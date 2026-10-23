import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from auto_rss_sorting import state
from auto_rss_sorting.state import (
    PublishedEntry,
    StateError,
    load_state,
    save_state,
    write_atomic,
)

PUBLISHED_AT = datetime(2026, 1, 14, 8, 0, tzinfo=UTC)


def entry(id: str, digest_date: date = date(2026, 1, 15)) -> PublishedEntry:
    return PublishedEntry(
        id=id, article_published_at=PUBLISHED_AT, digest_date=digest_date
    )


def test_missing_file_is_an_empty_state(tmp_path: Path) -> None:
    assert load_state(tmp_path / "published.json") == []


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state" / "published.json"  # parent created on save
    entries = [entry("https://a.com"), entry("https://b.com")]

    save_state(path, entries)

    assert load_state(path) == entries


def test_file_is_sorted_by_digest_date_then_id(tmp_path: Path) -> None:
    path = tmp_path / "published.json"
    save_state(
        path,
        [
            entry("https://b.com", date(2026, 1, 15)),
            entry("https://c.com", date(2026, 1, 14)),
            entry("https://a.com", date(2026, 1, 15)),
        ],
    )

    data = json.loads(path.read_text(encoding="utf-8"))

    assert [item["id"] for item in data] == [
        "https://c.com",
        "https://a.com",
        "https://b.com",
    ]
    assert data[0] == {
        "id": "https://c.com",
        "article_published_at": "2026-01-14T08:00:00Z",
        "digest_date": "2026-01-14",
    }


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        '[{"id": "https://a.com", "digest_date": "2026-01-15"}]',  # missing field
        # naive date: the time zone is unknown
        (
            '[{"id": "https://a.com", "article_published_at": "2026-01-14T08:00:00",'
            ' "digest_date": "2026-01-15"}]'
        ),
    ],
)
def test_invalid_file_raises_a_clear_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "published.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(StateError, match=r"^published\.json: "):
        load_state(path)


def test_failed_write_leaves_the_original_file_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "published.json"
    path.write_text("original", encoding="utf-8")

    def failing_replace(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(state.os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        write_atomic(path, "new content")

    assert path.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["published.json"]
