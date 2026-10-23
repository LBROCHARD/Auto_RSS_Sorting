from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from auto_rss_sorting.digest import (
    RunReport,
    already_published,
    digest_path,
    publish,
    render_digest,
)
from auto_rss_sorting.feeds import Article
from auto_rss_sorting.llm import LLMScore
from auto_rss_sorting.state import (
    PublishedEntry,
    drop_digest_date,
    load_state,
    save_state,
)

TODAY = date(2026, 1, 15)
NO_PROBLEM = RunReport(
    failed_feeds=[], skipped_undated=0, skipped_invalid=0, skipped_transient=0
)


def make_article(
    title: str = "Rust 2.0 is out", url: str = "https://example.com/rust-2"
) -> Article:
    return Article(
        id=url,
        url=url,
        title=title,
        description="",
        published_at=datetime(2026, 1, 15, 8, 0, tzinfo=UTC),
        source="Lobsters",
    )


def make_score(
    score: int = 8,
    summary: str = "Rust 2.0 is released.",
    reason: str = "Rust is a core interest.",
) -> LLMScore:
    return LLMScore(score=score, summary=summary, reason=reason)


def test_renders_an_article_with_every_field_and_the_footer() -> None:
    report = RunReport(
        failed_feeds=[], skipped_undated=3, skipped_invalid=1, skipped_transient=0
    )

    text = render_digest(TODAY, [(make_article(), make_score())], report)

    assert text == (
        "# Digest 2026-01-15\n"
        "\n"
        "## 1. Rust 2.0 is out\n"
        "\n"
        "- **Source:** Lobsters\n"
        "- **Score:** 8/10\n"
        "- **Link:** <https://example.com/rust-2>\n"
        "\n"
        "**Summary:** Rust 2.0 is released.\n"
        "\n"
        "**Reason:** Rust is a core interest.\n"
        "\n"
        "---\n"
        "\n"
        "## Report\n"
        "\n"
        "- **Failed feeds:** none\n"
        "- **Skipped articles:** 3 without date, 1 invalid LLM response, "
        "0 transient LLM error\n"
    )


def test_ranks_follow_the_given_order() -> None:
    ranked = [
        (make_article("First", "https://a.com"), make_score(9)),
        (make_article("Second", "https://b.com"), make_score(7)),
    ]

    text = render_digest(TODAY, ranked, NO_PROBLEM)

    assert "## 1. First\n" in text
    assert "## 2. Second\n" in text
    assert text.index("## 1. First") < text.index("## 2. Second")


def test_footer_lists_the_failed_feeds() -> None:
    report = RunReport(
        failed_feeds=["Lobsters", "Hacker News"],
        skipped_undated=0,
        skipped_invalid=0,
        skipped_transient=2,
    )

    text = render_digest(TODAY, [(make_article(), make_score())], report)

    assert "- **Failed feeds:** Lobsters, Hacker News\n" in text
    assert "2 transient LLM error" in text


def test_no_article_writes_the_message_and_the_footer() -> None:
    text = render_digest(TODAY, [], NO_PROBLEM)

    assert text.startswith("# Digest 2026-01-15\n\nNo new articles today.\n")
    assert "## 1." not in text
    assert "## Report\n" in text
    assert "- **Failed feeds:** none\n" in text


def test_markdown_in_article_and_llm_text_is_escaped() -> None:
    article = make_article(title="# [Click](https://evil.com) *now* <b>")
    score = make_score(summary="See [this](https://evil.com)", reason="`code` _x_")

    text = render_digest(TODAY, [(article, score)], NO_PROBLEM)

    assert r"## 1. \# \[Click\](https://evil.com) \*now\* \<b\>" in text
    assert r"**Summary:** See \[this\](https://evil.com)" in text
    assert r"**Reason:** \`code\` \_x\_" in text


def test_line_breaks_cannot_create_new_sections() -> None:
    article = make_article(title="Title\n## Injected")
    score = make_score(summary="Line one.\n\n## Fake heading", reason="A\nB")

    text = render_digest(TODAY, [(article, score)], NO_PROBLEM)

    assert r"## 1. Title \#\# Injected" in text
    assert r"**Summary:** Line one. \#\# Fake heading" in text
    assert "**Reason:** A B\n" in text


def test_digest_path_is_named_after_the_day(tmp_path: Path) -> None:
    assert digest_path(tmp_path, TODAY) == tmp_path / "2026-01-15.md"


def test_already_published_when_today_digest_exists(tmp_path: Path) -> None:
    assert not already_published(tmp_path, TODAY)
    (tmp_path / "2026-01-15.md").write_text("digest", encoding="utf-8")
    assert already_published(tmp_path, TODAY)


def test_publish_writes_the_digest_then_the_state(tmp_path: Path) -> None:
    digests_dir = tmp_path / "digests"
    state_path = tmp_path / "state" / "published.json"
    article = make_article()

    publish(digests_dir, state_path, TODAY, [(article, make_score())], NO_PROBLEM, [])

    text = (digests_dir / "2026-01-15.md").read_text(encoding="utf-8")
    assert text == render_digest(TODAY, [(article, make_score())], NO_PROBLEM)
    assert load_state(state_path) == [
        PublishedEntry(
            id=article.id,
            article_published_at=article.published_at,
            digest_date=TODAY,
        )
    ]


def test_state_is_untouched_when_the_digest_cannot_be_written(
    tmp_path: Path,
) -> None:
    digests_dir = tmp_path / "digests"
    digests_dir.write_text("a file where the directory should be", encoding="utf-8")
    state_path = tmp_path / "published.json"
    save_state(state_path, [])
    before = state_path.read_text(encoding="utf-8")

    with pytest.raises(OSError):
        publish(
            digests_dir,
            state_path,
            TODAY,
            [(make_article(), make_score())],
            NO_PROBLEM,
            [],
        )

    assert state_path.read_text(encoding="utf-8") == before


def test_force_rerun_overwrites_the_digest_without_duplicate_entries(
    tmp_path: Path,
) -> None:
    digests_dir = tmp_path / "digests"
    state_path = tmp_path / "published.json"
    first = make_article("First", "https://a.com")
    second = make_article("Second", "https://b.com")
    publish(digests_dir, state_path, TODAY, [(first, make_score())], NO_PROBLEM, [])

    # --force: today's entries are dropped, so "First" is a candidate again.
    entries = drop_digest_date(load_state(state_path), TODAY)
    ranked = [(first, make_score()), (second, make_score())]
    publish(digests_dir, state_path, TODAY, ranked, NO_PROBLEM, entries)

    text = (digests_dir / "2026-01-15.md").read_text(encoding="utf-8")
    assert "## 2. Second" in text
    assert [e.id for e in load_state(state_path)] == ["https://a.com", "https://b.com"]


def test_link_cannot_close_the_autolink() -> None:
    article = make_article(url="https://x.com/a> [free](https://evil.com) <b\nc")

    text = render_digest(TODAY, [(article, make_score())], NO_PROBLEM)

    assert (
        "- **Link:** <https://x.com/a%3E%20[free](https://evil.com)%20%3Cb%0Ac>\n"
        in text
    )
