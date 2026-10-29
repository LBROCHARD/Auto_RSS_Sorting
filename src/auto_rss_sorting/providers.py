"""LLM provider adapters and the registry that picks one from config.yaml."""

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import partial
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

REQUEST_TIMEOUT_SECONDS = 30
# Stable scores between runs and for eval.
TEMPERATURE = 0
# A score, a one or two sentence summary and a reason fit well within this.
MAX_OUTPUT_TOKENS = 500
# Guarantees syntactically valid JSON (the shared prompt already asks for it):
# without it the model sometimes drops a comma, and at temperature 0 the retry
# returns the same malformed answer. Pydantic still checks the fields.
RESPONSE_FORMAT = {"type": "json_object"}
ERROR_BODY_MAX_CHARS = 300
# 401 bad key, 402 quota exhausted (payment required), 403 no access, 404 unknown model.
FATAL_STATUSES = {401, 402, 403, 404}


@dataclass(frozen=True)
class ChatAPI:
    """What differs between two providers of the OpenAI-style chat completions API."""

    name: str
    # A constant, not a config value: the API key is only ever sent to this host.
    url: str
    # Kept between the starts of two calls so the free tier does not answer 429.
    min_interval_seconds: float
    # Request fields only this provider understands.
    extra_body: Mapping[str, object] = field(default_factory=dict)


# The free tier allows 0.5 request/s.
MISTRAL = ChatAPI(
    name="Mistral",
    url="https://api.mistral.ai/v1/chat/completions",
    min_interval_seconds=2.0,
)
# The free tier of gemini-3.5-flash-lite allows 15 requests/min (AI Studio
# console, 2026-10-29). Gemini 3 models always think before answering: kept
# low so the thinking does not eat the MAX_OUTPUT_TOKENS answer budget.
GEMINI = ChatAPI(
    name="Gemini",
    url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    min_interval_seconds=4.0,
    extra_body={"reasoning_effort": "low"},
)


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


class ChatCompletionsProvider:
    """An OpenAI-style chat completions API, called with plain httpx."""

    def __init__(
        self,
        api: ChatAPI,
        model: str,
        api_key: str,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api = api
        self.model = model
        # Sent only in the Authorization header, never in the URL: httpx logs URLs.
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    def complete(self, system: str, user: str) -> Completion:
        self._wait_for_rate_limit()
        # Started after the wait: the free-tier pacing is not latency.
        started = self._clock()
        try:
            response = self._client.post(
                self.api.url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                # Provider-only fields first: they can add to the request,
                # never replace the fields every provider shares.
                json={
                    **self.api.extra_body,
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "response_format": RESPONSE_FORMAT,
                },
            )
        except httpx.TransportError as error:
            raise TransientProviderError(f"{self.api.name} API: {error!r}") from error
        latency_seconds = self._clock() - started

        status = response.status_code
        if status == 429 or status >= 500:
            raise TransientProviderError(self._describe_error(response))
        # Bad key, exhausted quota, no access or unknown model: every following
        # article would fail the same way, so the run fails.
        if status in FATAL_STATUSES:
            raise FatalProviderError(self._describe_error(response))
        # Other 4xx (400, 413, 422) may come from this article only: skip it.
        # If they are systematic, no article is scored and the run fails anyway.
        if status >= 400:
            raise InvalidResponseError(self._describe_error(response))

        try:
            body = _ChatResponse.model_validate_json(response.content)
        except ValidationError as error:
            raise InvalidResponseError(
                f"unexpected {self.api.name} response body: {error}"
            ) from error
        return Completion(
            text=body.choices[0].message.content,
            input_tokens=body.usage.prompt_tokens,
            output_tokens=body.usage.completion_tokens,
            latency_seconds=latency_seconds,
        )

    def _wait_for_rate_limit(self) -> None:
        """Keep at least the API's minimum interval between the starts of two
        calls, failed calls included."""
        if self._last_call is not None:
            elapsed = self._clock() - self._last_call
            wait = self.api.min_interval_seconds - elapsed
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _describe_error(self, response: httpx.Response) -> str:
        """Status code and the provider's error body, never the request headers."""
        return (
            f"{self.api.name} API returned {response.status_code}: "
            f"{response.text[:ERROR_BODY_MAX_CHARS]}"
        )


# Provider name in config.yaml -> (API key environment variable, adapter).
PROVIDERS: dict[str, tuple[str, Callable[[str, str], Provider]]] = {
    "gemini": ("GEMINI_API_KEY", partial(ChatCompletionsProvider, GEMINI)),
    "mistral": ("MISTRAL_API_KEY", partial(ChatCompletionsProvider, MISTRAL)),
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
