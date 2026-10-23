import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from auto_rss_sorting import state
from auto_rss_sorting.feeds import Article
from auto_rss_sorting.state import (
    PublishedEntry,
    StateError,
    add_published,
    drop_digest_date,
    exclude_published,
    load_state,
    purge,
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


NOW = datetime(2026, 1, 15, 6, 0, tzinfo=UTC)
TODAY = NOW.date()


def published(id: str, published_at: datetime) -> PublishedEntry:
    return PublishedEntry(
        id=id, article_published_at=published_at, digest_date=date(2026, 1, 10)
    )


def make_article(id: str) -> Article:
    return Article(
        id=id,
        url=id,
        title="Title",
        description="",
        published_at=PUBLISHED_AT,
        source="Example",
    )


def test_purge_drops_entries_older_than_max_age() -> None:
    limit = NOW - timedelta(days=7)
    entries = [
        published("https://old.com", limit - timedelta(seconds=1)),
        published("https://limit.com", limit),  # same cutoff as the candidates
        published("https://recent.com", NOW - timedelta(days=1)),
    ]

    kept = purge(entries, NOW, max_age_days=7)

    assert [e.id for e in kept] == ["https://limit.com", "https://recent.com"]


def test_drop_digest_date_removes_only_that_day() -> None:
    entries = [
        entry("https://a.com", TODAY),
        entry("https://b.com", TODAY - timedelta(days=1)),
        entry("https://c.com", TODAY),
    ]

    kept = drop_digest_date(entries, TODAY)

    assert [e.id for e in kept] == ["https://b.com"]


def test_exclude_published_keeps_the_others_in_order() -> None:
    candidates = [
        make_article("https://c.com"),
        make_article("https://a.com"),
        make_article("https://b.com"),
    ]

    kept = exclude_published(candidates, [entry("https://a.com")])

    assert [a.id for a in kept] == ["https://c.com", "https://b.com"]


def test_add_published_records_the_digest_articles() -> None:
    existing = [entry("https://old.com", TODAY - timedelta(days=1))]

    entries = add_published(existing, [make_article("https://a.com")], TODAY)

    assert entries == [
        existing[0],
        PublishedEntry(
            id="https://a.com", article_published_at=PUBLISHED_AT, digest_date=TODAY
        ),
    ]
