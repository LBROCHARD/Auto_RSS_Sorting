"""Render the day's digest as Markdown and publish it with the state."""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from auto_rss_sorting.feeds import Article
from auto_rss_sorting.llm import LLMScore
from auto_rss_sorting.state import (
    PublishedEntry,
    add_published,
    save_state,
    write_atomic,
)

# Characters that could turn untrusted text into a heading, a link, emphasis
# or HTML once rendered.
MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]<>#])")


@dataclass(frozen=True)
class RunReport:
    failed_feeds: list[str]
    skipped_undated: int
    skipped_invalid: int
    skipped_transient: int


def render_digest(
    today: date, ranked: list[tuple[Article, LLMScore]], report: RunReport
) -> str:
    """Return the digest: one section per article in the given order, then the
    footer, which is always present."""
    parts = [f"# Digest {today.isoformat()}\n"]
    if not ranked:
        parts.append("No new articles today.\n")
    for rank, (article, score) in enumerate(ranked, start=1):
        parts.append(
            f"## {rank}. {_inline(article.title)}\n"
            "\n"
            f"- **Source:** {article.source}\n"
            f"- **Score:** {score.score}/10\n"
            f"- **Link:** <{article.url}>\n"
            "\n"
            f"**Summary:** {_inline(score.summary)}\n"
            "\n"
            f"**Reason:** {_inline(score.reason)}\n"
        )
    failed = ", ".join(report.failed_feeds) or "none"
    parts.append(
        "---\n"
        "\n"
        "## Report\n"
        "\n"
        f"- **Failed feeds:** {failed}\n"
        f"- **Skipped articles:** {report.skipped_undated} without date, "
        f"{report.skipped_invalid} invalid LLM response, "
        f"{report.skipped_transient} transient LLM error\n"
    )
    return "\n".join(parts)


def _inline(text: str) -> str:
    """Untrusted text on a single line, with Markdown characters escaped."""
    return MARKDOWN_SPECIAL.sub(r"\\\1", " ".join(text.split()))


def digest_path(digests_dir: Path, today: date) -> Path:
    return digests_dir / f"{today.isoformat()}.md"


def already_published(digests_dir: Path, today: date) -> bool:
    """Today's digest exists: a same-day re-run exits without changes."""
    return digest_path(digests_dir, today).exists()


def publish(
    digests_dir: Path,
    state_path: Path,
    today: date,
    ranked: list[tuple[Article, LLMScore]],
    report: RunReport,
    entries: list[PublishedEntry],
) -> None:
    """Write the digest, then the state with today's articles added. The state
    is only written once the digest is, so a failed digest changes nothing."""
    write_atomic(digest_path(digests_dir, today), render_digest(today, ranked, report))
    articles = [article for article, _ in ranked]
    save_state(state_path, add_published(entries, articles, today))
