import json
from pathlib import Path

import pytest
from fake_provider import FakeProvider

from auto_rss_sorting.evaluation import EvalReport, Label, evaluate, load_labels
from auto_rss_sorting.inputs import InputError
from auto_rss_sorting.llm import (
    SYSTEM_PROMPT,
    FatalProviderError,
    ScoringFailedError,
    SkipReason,
    TransientProviderError,
)

HEADER = "url,title,description,score\n"
PROFILE = "Rust, databases."
INVALID = "not json"


def answer(score: int) -> str:
    return json.dumps({"score": score, "summary": "A summary.", "reason": "A reason."})


def label(score: int, n: int = 0, description: str = "") -> Label:
    return Label(
        url=f"https://example.com/{n}",
        title=f"Title {n}",
        description=description,
        score=score,
    )


def run_evaluate(labels: list[Label], responses: list[str | Exception]) -> EvalReport:
    return evaluate(
        FakeProvider(responses),
        PROFILE,
        labels,
        max_description_chars=2000,
        sleep=lambda _: None,
    )


def write_labels(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "labels.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_valid_labels_load_in_file_order(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path,
        HEADER
        + 'https://example.com/rust,Rust 2.0,"New release, with async",9\n'
        + "https://example.com/vide,Article sans description,,0\n",
    )

    labels = load_labels(path)

    assert [str(label.url) for label in labels] == [
        "https://example.com/rust",
        "https://example.com/vide",
    ]
    assert labels[0] == Label(
        url="https://example.com/rust",
        title="Rust 2.0",
        description="New release, with async",
        score=9,
    )
    assert labels[1].description == ""
    assert labels[1].score == 0


def test_byte_order_mark_is_ignored(tmp_path: Path) -> None:
    # Excel writes a BOM at the start of UTF-8 CSV files.
    path = write_labels(tmp_path, "﻿" + HEADER + "https://example.com/a,A,,5\n")

    assert len(load_labels(path)) == 1


def test_missing_labels_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match=r"labels\.csv.*not found"):
        load_labels(tmp_path / "labels.csv")


@pytest.mark.parametrize(
    "header",
    ["", "url,title,score\n", "url,title,description,score,extra\n"],
)
def test_wrong_header(tmp_path: Path, header: str) -> None:
    path = write_labels(tmp_path, header)

    with pytest.raises(
        InputError, match=r"labels\.csv: .*header.*url,title,description,score"
    ):
        load_labels(path)


def test_header_only(tmp_path: Path) -> None:
    path = write_labels(tmp_path, HEADER)

    with pytest.raises(InputError, match=r"labels\.csv: .*no label"):
        load_labels(path)


@pytest.mark.parametrize("score", ["11", "-1", "7.5", "abc", ""])
def test_invalid_score(tmp_path: Path, score: str) -> None:
    path = write_labels(tmp_path, HEADER + f"https://example.com/a,A title,,{score}\n")

    with pytest.raises(InputError, match=r"labels\.csv: line 2: score: "):
        load_labels(path)


def test_empty_title(tmp_path: Path) -> None:
    path = write_labels(tmp_path, HEADER + "https://example.com/a,  ,,5\n")

    with pytest.raises(InputError, match=r"labels\.csv: line 2: title: "):
        load_labels(path)


@pytest.mark.parametrize("url", ["not a url", "ftp://example.com/a"])
def test_invalid_url(tmp_path: Path, url: str) -> None:
    path = write_labels(tmp_path, HEADER + f"{url},A title,,5\n")

    with pytest.raises(InputError, match=r"labels\.csv: line 2: url: "):
        load_labels(path)


def test_row_with_missing_fields(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path, HEADER + "https://example.com/a,A title,,5\nhttps://example.com/b\n"
    )

    with pytest.raises(InputError, match=r"labels\.csv: line 3: .*4 fields"):
        load_labels(path)


def test_duplicate_url_after_normalization(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path,
        HEADER
        + "https://example.com/a,First,,5\n"
        + "HTTPS://Example.com/a/?utm_source=rss,Same article,,6\n",
    )

    with pytest.raises(
        InputError, match=r"labels\.csv: line 3: duplicate URL.*example\.com/a"
    ):
        load_labels(path)


def test_a_difference_of_3_is_within_tolerance_4_is_not() -> None:
    labels = [label(5, n) for n in range(4)]

    report = run_evaluate(labels, [answer(8), answer(2), answer(9), answer(1)])

    assert [result.llm_score for result in report.results] == [8, 2, 9, 1]
    assert report.within_tolerance == 2
    assert report.accuracy == 0.5


def test_a_skipped_article_counts_as_a_miss() -> None:
    report = run_evaluate([label(5, 0), label(5, 1)], [INVALID, INVALID, answer(5)])

    assert report.results[0].llm_score is None
    assert report.results[0].skip_reason is SkipReason.INVALID_RESPONSE
    assert report.within_tolerance == 1
    assert report.accuracy == 0.5


def test_cost_counts_the_tokens_of_every_call_retries_included() -> None:
    # Two articles, three calls (one retry): 300 input and 60 output tokens.
    report = run_evaluate([label(5, 0), label(5, 1)], [INVALID, answer(5), answer(5)])

    assert report.calls == 3
    assert (report.input_tokens, report.output_tokens) == (300, 60)
    # (300 × 2 + 60 × 10) / 1,000,000 = 0.0012 for 2 articles, so 0.06 for 100.
    assert report.cost_per_100_articles(2.0, 10.0) == pytest.approx(0.06)


def test_free_provider_costs_nothing() -> None:
    report = run_evaluate([label(5)], [answer(5)])

    assert report.cost_per_100_articles(0.0, 0.0) == 0.0


def test_average_latency_over_completed_calls() -> None:
    # A transient error returns no completion, so it has no latency to count.
    report = run_evaluate(
        [label(5, 0), label(5, 1)],
        [TransientProviderError("429"), answer(5), INVALID, answer(5)],
    )

    assert report.calls == 3
    assert report.average_latency_seconds == pytest.approx(0.5)


def test_fatal_error_propagates() -> None:
    with pytest.raises(FatalProviderError):
        run_evaluate([label(5)], [FatalProviderError("401")])


def test_nothing_scored_fails() -> None:
    with pytest.raises(ScoringFailedError):
        run_evaluate([label(5)], [INVALID, INVALID])


def test_the_production_prompt_is_sent() -> None:
    provider = FakeProvider([answer(5)])

    evaluate(
        provider,
        PROFILE,
        [label(5, description="x" * 50)],
        max_description_chars=10,
        sleep=lambda _: None,
    )

    [(system, user)] = provider.calls
    assert system == SYSTEM_PROMPT.replace("{profile}", PROFILE)
    assert json.loads(user) == {
        "title": "Title 0",
        "source": "example.com",
        "description": "x" * 10,
    }
