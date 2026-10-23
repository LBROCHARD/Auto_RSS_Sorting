"""LLM provider adapters and the registry that picks one from config.yaml."""

import os
from collections.abc import Callable
from typing import Annotated

import httpx
from pydantic import BaseModel, Field, ValidationError

from auto_rss_sorting.inputs import Config, InputError
from auto_rss_sorting.llm import (
    Completion,
    FatalProviderError,
    InvalidResponseError,
    Provider,
    TransientProviderError,
)

# A constant, not a config value: the API key is only ever sent to this host.
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 30
# Stable scores between runs and for eval.
TEMPERATURE = 0
# A score, a one or two sentence summary and a reason fit well within this.
MAX_OUTPUT_TOKENS = 500
ERROR_BODY_MAX_CHARS = 300


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int


class _ChatResponse(BaseModel):
    choices: Annotated[list[_Choice], Field(min_length=1)]
    usage: _Usage


class MistralProvider:
    """Mistral chat completions API, called with plain httpx."""

    def __init__(
        self, model: str, api_key: str, client: httpx.Client | None = None
    ) -> None:
        self.model = model
        # Sent only in the Authorization header, never in the URL: httpx logs URLs.
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)

    def complete(self, system: str, user: str) -> Completion:
        try:
            response = self._client.post(
                MISTRAL_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                },
            )
        except httpx.TransportError as error:
            raise TransientProviderError(f"Mistral API: {error!r}") from error

        status = response.status_code
        if status == 429 or status >= 500:
            raise TransientProviderError(_describe_error(response))
        # 401/403 (key), 402 (quota exhausted), other 4xx (bad request, unknown
        # model): retrying cannot help, and every following article would fail too.
        if status >= 400:
            raise FatalProviderError(_describe_error(response))

        try:
            body = _ChatResponse.model_validate_json(response.content)
        except ValidationError as error:
            raise InvalidResponseError(
                f"unexpected Mistral response body: {error}"
            ) from error
        return Completion(
            text=body.choices[0].message.content,
            input_tokens=body.usage.prompt_tokens,
            output_tokens=body.usage.completion_tokens,
        )


def _describe_error(response: httpx.Response) -> str:
    """Status code and the provider's error body, never the request headers."""
    return (
        f"Mistral API returned {response.status_code}: "
        f"{response.text[:ERROR_BODY_MAX_CHARS]}"
    )


# Provider name in config.yaml -> (API key environment variable, adapter).
PROVIDERS: dict[str, tuple[str, Callable[[str, str], Provider]]] = {
    "mistral": ("MISTRAL_API_KEY", MistralProvider),
}


def make_provider(config: Config) -> Provider:
    """Build the configured provider, failing fast on an unknown name or a
    missing API key."""
    if config.provider not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise InputError(
            f"config.yaml: provider: unknown provider {config.provider!r} "
            f"(known providers: {known})"
        )
    key_variable, adapter = PROVIDERS[config.provider]
    api_key = os.environ.get(key_variable, "").strip()
    if not api_key:
        raise InputError(
            f"{key_variable} is not set: the {config.provider!r} provider reads "
            "its API key from this environment variable"
        )
    return adapter(config.model, api_key)
