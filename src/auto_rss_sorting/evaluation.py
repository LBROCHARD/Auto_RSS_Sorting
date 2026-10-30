"""The `eval` subcommand: score hand-labelled articles and measure accuracy,
cost and latency of the configured provider."""

import csv
import io
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from auto_rss_sorting.candidates import normalize_url
from auto_rss_sorting.feeds import Article
from auto_rss_sorting.inputs import Config, InputError, NonEmptyStr, _read_text
from auto_rss_sorting.llm import (
    Completion,
    Provider,
    ScoringFailedError,
    SkipReason,
    score_article,
)

LABEL_COLUMNS = ["url", "title", "description", "score"]
# Spec: the LLM score must be within ±3 points of the human score...
TOLERANCE = 3
# ...for at least 80 % of the labelled articles.
TARGET_ACCURACY = 0.8
# The prompt does not use the publication date, and the CSV has none.
PLACEHOLDER_DATE = datetime(1970, 1, 1, tzinfo=UTC)


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


@dataclass(frozen=True)
class LabelResult:
    label: Label
    llm_score: int | None
    skip_reason: SkipReason | None

    @property
    def within_tolerance(self) -> bool:
        return (
            self.llm_score is not None
            and abs(self.llm_score - self.label.score) <= TOLERANCE
        )


@dataclass(frozen=True)
class EvalReport:
    results: list[LabelResult]
    input_tokens: int
    output_tokens: int
    # Completed calls, retries included: a call that raised returned no usage.
    calls: int
    total_latency_seconds: float

    @property
    def within_tolerance(self) -> int:
        return sum(result.within_tolerance for result in self.results)

    @property
    def accuracy(self) -> float:
        """Share of all labelled articles within tolerance: a skipped article
        counts as a miss."""
        return self.within_tolerance / len(self.results)

    @property
    def average_latency_seconds(self) -> float:
        return self.total_latency_seconds / self.calls

    def cost_per_100_articles(
        self, price_input_per_mtok: float, price_output_per_mtok: float
    ) -> float:
        cost = (
            self.input_tokens * price_input_per_mtok
            + self.output_tokens * price_output_per_mtok
        ) / 1_000_000
        return cost / len(self.results) * 100


class MeteredProvider:
    """Wraps a provider and adds up the usage and latency of every completed call."""

    def __init__(self, provider: Provider) -> None:
        self._provider = provider
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_latency_seconds = 0.0

    def complete(self, system: str, user: str) -> Completion:
        completion = self._provider.complete(system, user)
        self.calls += 1
        self.input_tokens += completion.input_tokens
        self.output_tokens += completion.output_tokens
        self.total_latency_seconds += completion.latency_seconds
        return completion


def label_to_article(label: Label) -> Article:
    """The labelled article as the pipeline sees it, so eval sends the exact
    production prompt. The URL's host stands in for the feed name."""
    url = str(label.url)
    return Article(
        id=normalize_url(url),
        url=url,
        title=label.title,
        description=label.description,
        published_at=PLACEHOLDER_DATE,
        source=label.url.host or url,
    )


def evaluate(
    provider: Provider,
    profile: str,
    labels: list[Label],
    max_description_chars: int,
    sleep: Callable[[float], None] = time.sleep,
) -> EvalReport:
    """Score every labelled article with the production prompt and retry rules.
    A FatalProviderError propagates; nothing scored raises ScoringFailedError."""
    metered = MeteredProvider(provider)
    results: list[LabelResult] = []
    for label in labels:
        result = score_article(
            metered, profile, label_to_article(label), max_description_chars, sleep
        )
        if isinstance(result, SkipReason):
            results.append(LabelResult(label, llm_score=None, skip_reason=result))
        else:
            results.append(LabelResult(label, llm_score=result.score, skip_reason=None))
    if all(result.llm_score is None for result in results):
        raise ScoringFailedError(
            f"none of the {len(labels)} labelled articles could be scored, "
            "see warnings above"
        )
    return EvalReport(
        results=results,
        input_tokens=metered.input_tokens,
        output_tokens=metered.output_tokens,
        calls=metered.calls,
        total_latency_seconds=metered.total_latency_seconds,
    )


def format_report(report: EvalReport, config: Config) -> str:
    """The eval result as plain text: one line per article, in file order, so
    disagreements are visible, then the three metrics."""
    lines = [
        f"eval: {config.provider} / {config.model}, {len(report.results)} articles",
        "human  llm  diff  title",
    ]
    for result in report.results:
        human = result.label.score
        if result.llm_score is None:
            lines.append(
                f"{human:>5}  {'-':>3}  {'-':>4}  {result.label.title} "
                f"(skipped: {result.skip_reason.value})"
            )
        else:
            diff = result.llm_score - human
            lines.append(
                f"{human:>5}  {result.llm_score:>3}  {diff:>+4}  {result.label.title}"
            )
    met = "met" if report.accuracy >= TARGET_ACCURACY else "not met"
    cost = report.cost_per_100_articles(
        config.price_input_per_mtok, config.price_output_per_mtok
    )
    accuracy = (
        f"accuracy: {report.within_tolerance}/{len(report.results)} within "
        f"±{TOLERANCE} points ({report.accuracy * 100:.0f} %), "
        f"target {TARGET_ACCURACY * 100:.0f} %: {met}"
    )
    usage = (
        f"cost: {cost:.4f} per 100 articles ({report.input_tokens:,} input tokens, "
        f"{report.output_tokens:,} output tokens)"
    )
    latency = (
        f"latency: {report.average_latency_seconds:.2f} s per call on average "
        f"({report.calls} calls)"
    )
    return "\n".join([*lines, accuracy, usage, latency])
