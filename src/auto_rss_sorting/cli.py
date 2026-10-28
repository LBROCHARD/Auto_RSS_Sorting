"""The `auto-rss-sorting` command and the daily run: every step of the
pipeline, in order."""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from auto_rss_sorting.candidates import collect_candidates
from auto_rss_sorting.digest import RunReport, already_published, digest_path, publish
from auto_rss_sorting.evaluation import evaluate, format_report, load_labels
from auto_rss_sorting.feeds import fetch_all, make_http_client
from auto_rss_sorting.inputs import InputError, Inputs, load_inputs
from auto_rss_sorting.llm import (
    FatalProviderError,
    Provider,
    ScoringFailedError,
    score_articles,
)
from auto_rss_sorting.providers import make_provider
from auto_rss_sorting.ranking import compile_keywords, prefilter, top_articles
from auto_rss_sorting.state import (
    StateError,
    drop_digest_date,
    exclude_published,
    load_state,
    purge,
)

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# The failures the run expects: reported as one line, without a traceback.
# Any other exception is a bug and keeps its traceback.
RUN_ERRORS = (InputError, StateError, FatalProviderError, ScoringFailedError)


def main(argv: list[str] | None = None) -> int:
    """Entry point: read the inputs from the current directory, publish today's
    digest. Returns the exit code: 0 on success, 1 if the run failed."""
    parser = argparse.ArgumentParser(
        prog="auto-rss-sorting",
        description="Publish today's digest of the best articles from the feeds.",
    )
    parser.add_argument(
        "--force", action="store_true", help="regenerate today's digest"
    )
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser(
        "eval",
        help="score eval/labels.csv with the configured provider and report "
        "accuracy, cost and latency",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    # The only place that reads the clock.
    now = datetime.now(UTC)
    base_dir = Path.cwd()
    try:
        inputs = load_inputs(base_dir)
        provider = make_provider(inputs.config)
        if args.command == "eval":
            run_eval(inputs, provider, base_dir)
        else:
            with make_http_client() as client:
                run(inputs, provider, client, base_dir, now, args.force)
    except RUN_ERRORS as error:
        logger.error("run failed: %s", error)
        return 1
    return 0


def run_eval(inputs: Inputs, provider: Provider, base_dir: Path) -> None:
    """Score the hand-labelled articles and print the report. Fetches no feed
    and never touches the digests or the state."""
    labels = load_labels(base_dir / "eval" / "labels.csv")
    report = evaluate(
        provider, inputs.profile, labels, inputs.config.max_description_chars
    )
    print(format_report(report, inputs.config))


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
