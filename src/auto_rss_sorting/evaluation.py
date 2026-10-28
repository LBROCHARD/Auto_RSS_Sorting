"""The `eval` subcommand: score hand-labelled articles and measure accuracy,
cost and latency of the configured provider."""

import csv
import io
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from auto_rss_sorting.candidates import normalize_url
from auto_rss_sorting.inputs import InputError, NonEmptyStr, _read_text

LABEL_COLUMNS = ["url", "title", "description", "score"]


class Label(BaseModel):
    """One hand-scored article of eval/labels.csv."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: HttpUrl
    title: NonEmptyStr
    description: str
    score: Annotated[int, Field(ge=0, le=10)]


def load_labels(path: Path) -> list[Label]:
    """Load the hand-scored articles, in file order. Fails with a message naming
    the file and the line on the first invalid row."""
    # Excel writes a byte order mark at the start of UTF-8 CSV files.
    text = _read_text(path).removeprefix("﻿")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header != LABEL_COLUMNS:
        raise InputError(
            f"{path.name}: the header must be {','.join(LABEL_COLUMNS)}, "
            f"got {','.join(header or [])!r}"
        )

    labels: list[Label] = []
    seen: set[str] = set()
    for row in reader:
        if not row:
            continue
        where = f"{path.name}: line {reader.line_num}"
        if len(row) != len(LABEL_COLUMNS):
            raise InputError(
                f"{where}: expected {len(LABEL_COLUMNS)} fields, got {len(row)}"
            )
        try:
            label = Label.model_validate(dict(zip(LABEL_COLUMNS, row, strict=True)))
        except ValidationError as error:
            raise InputError(
                "\n".join(
                    f"{where}: {'.'.join(str(part) for part in detail['loc'])}: "
                    f"{detail['msg']}"
                    for detail in error.errors()
                )
            ) from error
        article_id = normalize_url(str(label.url))
        if article_id in seen:
            raise InputError(f"{where}: duplicate URL {article_id!r}")
        seen.add(article_id)
        labels.append(label)

    if not labels:
        raise InputError(f"{path.name}: no label found below the header")
    return labels
