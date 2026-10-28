import json
from collections.abc import Callable

import httpx
import pytest

from auto_rss_sorting.inputs import Config, InputError
from auto_rss_sorting.llm import (
    Completion,
    FatalProviderError,
    InvalidResponseError,
    TransientProviderError,
)
from auto_rss_sorting.providers import (
    MIN_INTERVAL_SECONDS,
    MISTRAL_URL,
    MistralProvider,
    make_provider,
)

FAKE_KEY = "fake-key"
OK_BODY = {
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
}


class FakeClock:
    """A monotonic clock that only moves when told to, or when slept on."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_mistral(
    handler: Callable[[httpx.Request], httpx.Response],
    clock: FakeClock | None = None,
) -> MistralProvider:
    clock = clock or FakeClock()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return MistralProvider(
        "ministral-14b-2512", FAKE_KEY, client=client, clock=clock, sleep=clock.sleep
    )


def make_config(provider: str = "mistral") -> Config:
    return Config.model_validate(
        {
            "top_n": 10,
            "max_age_days": 7,
            "llm_max_articles": 50,
            "max_description_chars": 2000,
            "provider": provider,
            "model": "ministral-14b-2512",
            "price_input_per_mtok": 0.0,
            "price_output_per_mtok": 0.0,
        }
    )


def test_returns_text_and_token_usage() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=OK_BODY)

    completion = make_mistral(handler).complete("the system", "the user")

    assert completion == Completion(
        text="{}", input_tokens=120, output_tokens=30, latency_seconds=0.0
    )
    [request] = requests
    assert str(request.url) == MISTRAL_URL
    assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "ministral-14b-2512"
    assert body["messages"] == [
        {"role": "system", "content": "the system"},
        {"role": "user", "content": "the user"},
    ]


def test_requests_json_mode() -> None:
    # Without it, ministral-14b sometimes drops a comma between two values,
    # and at temperature 0 the retry returns the same malformed JSON.
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=OK_BODY)

    make_mistral(handler).complete("the system", "the user")

    [request] = requests
    assert json.loads(request.content)["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("status", [429, 500, 503])
def test_rate_limit_and_server_errors_are_transient(status: int) -> None:
    provider = make_mistral(lambda _: httpx.Response(status, json={"message": "x"}))
    with pytest.raises(TransientProviderError, match=str(status)):
        provider.complete("s", "u")


def test_timeout_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(TransientProviderError):
        make_mistral(handler).complete("s", "u")


# 402 is Mistral's "payment required" (quota exhausted); 404 is an unknown model.
@pytest.mark.parametrize("status", [401, 402, 403, 404])
def test_auth_quota_and_unknown_model_errors_are_fatal(status: int) -> None:
    body = {"message": "Unauthorized", "type": "authentication_error"}
    provider = make_mistral(lambda _: httpx.Response(status, json=body))
    with pytest.raises(FatalProviderError, match=str(status)) as error:
        provider.complete("s", "u")
    assert "Unauthorized" in str(error.value)
    assert FAKE_KEY not in str(error.value)


# A request rejected because of one article must skip that article, not fail the run.
@pytest.mark.parametrize("status", [400, 413, 422])
def test_other_client_errors_are_invalid_responses(status: int) -> None:
    body = {"message": "Bad request", "type": "invalid_request_error"}
    provider = make_mistral(lambda _: httpx.Response(status, json=body))
    with pytest.raises(InvalidResponseError, match=str(status)) as error:
        provider.complete("s", "u")
    assert FAKE_KEY not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [{"choices": []}, {"usage": {}}, {"choices": [{"message": {"content": None}}]}],
)
def test_malformed_success_body_is_an_invalid_response(body: dict) -> None:
    provider = make_mistral(lambda _: httpx.Response(200, json=body))
    with pytest.raises(InvalidResponseError):
        provider.complete("s", "u")


def test_make_provider_builds_the_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", FAKE_KEY)
    assert isinstance(make_provider(make_config()), MistralProvider)


def test_unknown_provider_lists_the_known_ones() -> None:
    with pytest.raises(InputError, match="unknown provider 'nope'.*mistral"):
        make_provider(make_config(provider="nope"))


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_api_key_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    else:
        monkeypatch.setenv("MISTRAL_API_KEY", value)
    with pytest.raises(InputError, match="MISTRAL_API_KEY"):
        make_provider(make_config())


def test_calls_are_spaced_by_the_minimum_interval() -> None:
    clock = FakeClock()
    provider = make_mistral(lambda _: httpx.Response(200, json=OK_BODY), clock)

    provider.complete("s", "u")
    assert clock.sleeps == []

    clock.now += 0.5
    provider.complete("s", "u")
    assert clock.sleeps == [pytest.approx(MIN_INTERVAL_SECONDS - 0.5)]

    clock.now += MIN_INTERVAL_SECONDS + 1
    provider.complete("s", "u")
    assert len(clock.sleeps) == 1


def test_latency_is_the_request_time_without_the_pacing_wait() -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        clock.now += 0.8  # the request takes 0.8 s
        return httpx.Response(200, json=OK_BODY)

    provider = make_mistral(handler, clock)
    assert provider.complete("s", "u").latency_seconds == pytest.approx(0.8)

    # The next call waits for the interval first: the wait is not latency.
    second = provider.complete("s", "u")
    assert clock.sleeps == [pytest.approx(MIN_INTERVAL_SECONDS - 0.8)]
    assert second.latency_seconds == pytest.approx(0.8)


def test_failed_calls_also_count_for_the_interval() -> None:
    clock = FakeClock()
    provider = make_mistral(lambda _: httpx.Response(429, json={}), clock)
    with pytest.raises(TransientProviderError):
        provider.complete("s", "u")
    with pytest.raises(TransientProviderError):
        provider.complete("s", "u")
    assert clock.sleeps == [pytest.approx(MIN_INTERVAL_SECONDS)]
