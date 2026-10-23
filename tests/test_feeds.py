import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_rss_sorting.feeds import FeedError, html_to_text, parse_feed
from auto_rss_sorting.inputs import Feed

FIXTURES = Path(__file__).parent / "fixtures"
FEED = Feed.model_validate({"name": "Example", "url": "https://example.com/feed"})


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<p>Hello <b>world</b></p>", "Hello world"),
        ('<a href="https://example.com">link</a>, then text', "link, then text"),
        ("<p>First</p><p>Second</p>", "First Second"),
        ("one<br>two<br/>three", "one two three"),
        ("<ul><li>a</li><li>b</li></ul>", "a b"),
    ],
)
def test_removes_tags(html: str, expected: str) -> None:
    assert html_to_text(html) == expected


def test_unescapes_entities() -> None:
    assert html_to_text("Tom &amp; Jerry, caf&eacute; &#8217;") == "Tom & Jerry, café ’"


def test_collapses_whitespace() -> None:
    assert html_to_text("  <p>a\n\n  b\t c</p>  ") == "a b c"


def test_drops_script_and_style_content() -> None:
    html = "<style>p { color: red }</style>Text<script>alert(1)</script>"
    assert html_to_text(html) == "Text"


def test_plain_text_is_unchanged() -> None:
    assert html_to_text("Just plain text.") == "Just plain text."


def test_empty_string() -> None:
    assert html_to_text("") == ""


def test_parses_rss_items() -> None:
    parsed = parse_feed(FEED, fixture("rss_valid.xml"))

    first, second = parsed.articles
    assert first.id == "https://example.com/rust-2"
    assert first.url == "https://Example.com/rust-2/?utm_source=rss"
    assert first.title == "Rust 2.0 is out"
    assert first.description == "Big news for Rust & friends."
    assert first.source == "Example"
    assert second.title == "Plain post"
    assert second.description == "Plain text description."
    assert parsed.undated_count == 0


def test_dates_are_converted_to_utc() -> None:
    first, second = parse_feed(FEED, fixture("rss_valid.xml")).articles

    assert first.published_at == datetime(2026, 10, 19, 8, 0, tzinfo=UTC)
    assert second.published_at == datetime(2026, 10, 18, 23, 30, tzinfo=UTC)


def test_parses_atom_entries() -> None:
    both, updated_only = parse_feed(FEED, fixture("atom_valid.xml")).articles

    assert both.id == "https://example.org/both"
    assert both.description == "Summary text."
    assert updated_only.description == "Content body."


def test_published_date_wins_over_updated() -> None:
    both, _ = parse_feed(FEED, fixture("atom_valid.xml")).articles

    assert both.published_at == datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def test_falls_back_to_updated_date() -> None:
    _, updated_only = parse_feed(FEED, fixture("atom_valid.xml")).articles

    assert updated_only.published_at == datetime(2026, 10, 17, 8, 30, tzinfo=UTC)


def test_entry_without_date_is_excluded_and_counted() -> None:
    parsed = parse_feed(FEED, fixture("missing_fields.xml"))

    assert "No date" not in [article.title for article in parsed.articles]
    assert parsed.undated_count == 1


def test_entry_without_description_has_empty_description() -> None:
    articles = parse_feed(FEED, fixture("missing_fields.xml")).articles

    [article] = [a for a in articles if a.title == "No description"]
    assert article.description == ""


def test_entry_without_title_has_empty_title() -> None:
    articles = parse_feed(FEED, fixture("missing_fields.xml")).articles

    [article] = [a for a in articles if a.id == "https://example.com/no-title"]
    assert article.title == ""


def test_entry_without_link_is_skipped_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        articles = parse_feed(FEED, fixture("missing_fields.xml")).articles

    assert "No link" not in [article.title for article in articles]
    assert len(articles) == 2
    assert "Example" in caplog.text
    assert "No link" in caplog.text


def test_empty_feed_has_no_articles() -> None:
    parsed = parse_feed(FEED, fixture("empty.xml"))

    assert parsed.articles == []
    assert parsed.undated_count == 0


def test_invalid_xml_raises_feed_error() -> None:
    with pytest.raises(FeedError, match="Example"):
        parse_feed(FEED, fixture("invalid.xml"))


def test_malformed_feed_with_entries_is_kept_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        articles = parse_feed(FEED, fixture("malformed_with_items.xml")).articles

    assert [article.id for article in articles] == ["https://example.com/readable"]
    assert "Example" in caplog.text


def test_title_whitespace_is_collapsed() -> None:
    [article] = parse_feed(FEED, fixture("malformed_with_items.xml")).articles

    assert article.title == "Still readable item"
