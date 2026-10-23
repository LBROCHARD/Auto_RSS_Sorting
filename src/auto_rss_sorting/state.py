"""The state of already published articles, and atomic file writes."""

import os
import tempfile
from datetime import date
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, TypeAdapter, ValidationError

from auto_rss_sorting.inputs import NonEmptyStr


class StateError(Exception):
    """The state file cannot be read. The message names the file and the problem."""


class PublishedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyStr
    article_published_at: AwareDatetime
    digest_date: date


STATE_ADAPTER = TypeAdapter(list[PublishedEntry])


def load_state(path: Path) -> list[PublishedEntry]:
    """Load the state. A missing file is an empty state (first run)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as error:
        raise StateError(f"{path.name}: cannot read file: {error}") from error
    try:
        return STATE_ADAPTER.validate_json(text)
    except ValidationError as error:
        lines = [
            f"{path.name}: {'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
            for detail in error.errors()
        ]
        raise StateError("\n".join(lines)) from error


def save_state(path: Path, entries: list[PublishedEntry]) -> None:
    """Write the state atomically, sorted so the committed file has stable diffs."""
    ordered = sorted(entries, key=lambda e: (e.digest_date, e.id))
    write_atomic(path, STATE_ADAPTER.dump_json(ordered, indent=2).decode() + "\n")


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to a temp file next to `path`, then rename it over `path`.
    On failure the temp file is removed and `path` is left untouched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same directory as the target, so the rename stays on one filesystem.
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except OSError:
        Path(temp_name).unlink(missing_ok=True)
        raise
