"""Provider-agnostic LLM scoring: prompt, response validation, retry rules."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from auto_rss_sorting.inputs import NonEmptyStr

# An optional Markdown code fence around the JSON, with or without a language tag.
CODE_FENCE = re.compile(r"^```[\w-]*\s*\n(.*)\n\s*```$", re.DOTALL)


class InvalidResponseError(Exception):
    """The LLM response is not valid JSON or does not match `LLMScore`."""


class LLMScore(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    score: Annotated[StrictInt, Field(ge=0, le=10)]
    summary: NonEmptyStr
    reason: NonEmptyStr


def parse_response(text: str) -> LLMScore:
    """Validate the LLM response, tolerating a code fence around the JSON."""
    text = text.strip()
    if match := CODE_FENCE.match(text):
        text = match.group(1)
    try:
        return LLMScore.model_validate_json(text)
    except ValidationError as error:
        raise InvalidResponseError(f"invalid LLM response: {error}") from error
