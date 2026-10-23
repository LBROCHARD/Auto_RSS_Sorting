"""Load and validate the input files, failing fast with a clear message."""

from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    PositiveInt,
    StringConstraints,
    ValidationError,
    field_validator,
)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NonNegativeFloat = Annotated[float, Field(ge=0)]


class InputError(Exception):
    """An input file is missing or invalid. The message names the file and the problem."""


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    top_n: PositiveInt
    max_age_days: PositiveInt
    llm_max_articles: PositiveInt
    max_description_chars: PositiveInt
    provider: NonEmptyStr
    model: NonEmptyStr
    price_input_per_mtok: NonNegativeFloat
    price_output_per_mtok: NonNegativeFloat


class Feed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: NonEmptyStr
    url: HttpUrl


class FeedList(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    feeds: Annotated[list[Feed], Field(min_length=1)]

    @field_validator("feeds")
    @classmethod
    def names_and_urls_are_unique(cls, feeds: list[Feed]) -> list[Feed]:
        _reject_duplicates("feed name", [feed.name for feed in feeds])
        _reject_duplicates("feed URL", [str(feed.url) for feed in feeds])
        return feeds


class Keywords(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    keywords: Annotated[dict[NonEmptyStr, int], Field(min_length=1)]

    @field_validator("keywords")
    @classmethod
    def keywords_are_unique_ignoring_case(
        cls, keywords: dict[str, int]
    ) -> dict[str, int]:
        _reject_duplicates("keyword", [keyword.lower() for keyword in keywords])
        return keywords


def load_config(path: Path) -> Config:
    return _validate(Config, _load_yaml_mapping(path), path)


def load_feeds(path: Path) -> list[Feed]:
    return _validate(FeedList, _load_yaml_mapping(path), path).feeds


def load_keywords(path: Path) -> dict[str, int]:
    return _validate(Keywords, _load_yaml_mapping(path), path).keywords


def _reject_duplicates(label: str, values: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {label}: {value!r}")
        seen.add(value)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise InputError(f"{path.name}: file not found ({path})") from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise InputError(f"{path.name}: invalid YAML: {error}") from error
    if not isinstance(data, dict):
        found = "an empty file" if data is None else type(data).__name__
        raise InputError(
            f"{path.name}: the top level must be a mapping (key: value), got {found}"
        )
    return data


def _validate[M: BaseModel](model: type[M], data: dict[str, Any], path: Path) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        lines = [
            f"{path.name}: {'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
            for detail in error.errors()
        ]
        raise InputError("\n".join(lines)) from error
