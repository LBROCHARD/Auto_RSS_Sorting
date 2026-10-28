"""The daily run: every step of the pipeline, in order."""

import logging
from datetime import datetime
from pathlib import Path

import httpx

from auto_rss_sorting.candidates import collect_candidates
from auto_rss_sorting.digest import RunReport, already_published, digest_path, publish
from auto_rss_sorting.feeds import fetch_all
from auto_rss_sorting.inputs import Inputs
from auto_rss_sorting.llm import Provider, score_articles
from auto_rss_sorting.ranking import compile_keywords, prefilter, top_articles
from auto_rss_sorting.state import (
    drop_digest_date,
    exclude_published,
    load_state,
    purge,
)

logger = logging.getLogger(__name__)


def run(
    inputs: Inputs,
    provider: Provider,
    client: httpx.Client,
    base_dir: Path,
    now: datetime,
    force: bool,
) -> None:
    """Publish today's digest in `base_dir/digests` and update the state.
    Exits without changes if today's digest exists, unless `force`. Nothing is
    written if scoring fails."""
    config = inputs.config
    today = now.date()
    digests_dir = base_dir / "digests"
    state_path = base_dir / "state" / "published.json"

    # Loaded first: an invalid state fails the run even on a no-op day.
    entries = load_state(state_path)
    if already_published(digests_dir, today) and not force:
        logger.info(
            "%s already exists, nothing to do (use --force to regenerate it)",
            digest_path(digests_dir, today),
        )
        return
    if force:
        entries = drop_digest_date(entries, today)
    entries = purge(entries, now, config.max_age_days)

    fetched = fetch_all(client, inputs.feeds)
    candidates = collect_candidates(fetched.articles, now, config.max_age_days)
    candidates = exclude_published(candidates, entries)
    logger.info("%d new candidates", len(candidates))
    kept = prefilter(
        candidates, compile_keywords(inputs.keywords), config.llm_max_articles
    )
    scoring = score_articles(
        provider, inputs.profile, kept, config.max_description_chars
    )

    ranked = top_articles(scoring.scored, config.top_n)
    report = RunReport(
        failed_feeds=fetched.failed_feeds,
        skipped_undated=fetched.undated_count,
        skipped_invalid=scoring.skipped_invalid,
        skipped_transient=scoring.skipped_transient,
    )
    publish(digests_dir, state_path, today, ranked, report, entries)
    logger.info(
        "published %s: %d articles, %d failed feeds, skipped %d without date, "
        "%d invalid LLM response, %d transient LLM error",
        digest_path(digests_dir, today),
        len(ranked),
        len(report.failed_feeds),
        report.skipped_undated,
        report.skipped_invalid,
        report.skipped_transient,
    )
