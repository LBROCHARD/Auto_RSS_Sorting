import pytest

from auto_rss_sorting.llm import InvalidResponseError, LLMScore, parse_response


def test_parses_valid_json() -> None:
    text = '{"score": 7, "summary": "A summary.", "reason": "A reason."}'
    assert parse_response(text) == LLMScore(
        score=7, summary="A summary.", reason="A reason."
    )


@pytest.mark.parametrize(
    "text",
    [
        '```json\n{"score": 7, "summary": "s", "reason": "r"}\n```',
        '```\n{"score": 7, "summary": "s", "reason": "r"}\n```',
        '  {"score": 7, "summary": "s", "reason": "r"}\n',
    ],
)
def test_accepts_code_fence_and_surrounding_whitespace(text: str) -> None:
    assert parse_response(text).score == 7


def test_ignores_extra_fields() -> None:
    text = '{"score": 3, "summary": "s", "reason": "r", "language": "fr"}'
    assert parse_response(text).score == 3


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "",
        '{"score": 7, "summary": "s"',
        '["score", 7]',
        '{"score": 11, "summary": "s", "reason": "r"}',
        '{"score": -1, "summary": "s", "reason": "r"}',
        '{"score": 7.5, "summary": "s", "reason": "r"}',
        '{"score": "7", "summary": "s", "reason": "r"}',
        '{"score": true, "summary": "s", "reason": "r"}',
        '{"score": 7, "summary": "", "reason": "r"}',
        '{"score": 7, "summary": "s", "reason": "   "}',
        '{"score": 7, "summary": "s"}',
    ],
)
def test_rejects_invalid_response(text: str) -> None:
    with pytest.raises(InvalidResponseError):
        parse_response(text)
