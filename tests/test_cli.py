import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fake_provider import FakeProvider

from auto_rss_sorting.cli import main, run
from auto_rss_sorting.inputs import Inputs, load_inputs
from auto_rss_sorting.llm import FatalProviderError
from auto_rss_sorting.state import load_state

FIXTURES = Path(__file__).parent / "fixtures"
# Every fixture article (17 to 19 October 2026) is within max_age_days of this.
NOW = datetime(2026, 10, 21, 6, 0, tzinfo=UTC)

# feeds.yaml order: RSS, Atom, then a feed answering 404.
FEED_FILES = {
    "https://feeds.test/rss": "rss_valid.xml",
    "https://feeds.test/atom": "atom_valid.xml",
}
FEEDS_YAML = """\
feeds:
  - name: Example RSS
    url: https://feeds.test/rss
  - name: Example Atom
    url: https://feeds.test/atom
  - name: Missing
    url: https://feeds.test/missing
"""
CONFIG_YAML = """\
top_n: 3
max_age_days: 7
llm_max_articles: 50
max_description_chars: 2000
provider: fake
model: fake-model
price_input_per_mtok: 0
price_output_per_mtok: 0
"""
KEYWORDS_YAML = "keywords:\n  rust: 3\n"

# Pre-filter order: "rust" scores 3, then the others by date (desc).
RUST = "https://example.com/rust-2"
BOTH = "https://example.org/both"
PLAIN = "https://example.com/plain"
UPDATED = "https://example.org/updated-only"


def answer(score: int) -> str:
    return json.dumps({"score": score, "summary": "A summary.", "reason": "A reason."})


# One answer per article, in pre-filter order: rust, both, plain, updated.
# Final ranking with top_n 3: both (9), updated (7), rust (5); plain (2) is cut.
ANSWERS = [answer(5), answer(9), answer(2), answer(7)]


def write_inputs(base_dir: Path, config_yaml: str = CONFIG_YAML) -> None:
    (base_dir / "config.yaml").write_text(config_yaml, encoding="utf-8")
    (base_dir / "feeds.yaml").write_text(FEEDS_YAML, encoding="utf-8")
    (base_dir / "keywords.yaml").write_text(KEYWORDS_YAML, encoding="utf-8")
    (base_dir / "profile.md").write_text("I like Rust.\n", encoding="utf-8")


@pytest.fixture
def inputs(tmp_path: Path) -> Inputs:
    write_inputs(tmp_path)
    return load_inputs(tmp_path)


def serve_fixtures(request: httpx.Request) -> httpx.Response:
    name = FEED_FILES.get(str(request.url))
    if name is None:
        return httpx.Response(404)
    return httpx.Response(200, content=(FIXTURES / name).read_bytes())


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(serve_fixtures))


def digest_text(base_dir: Path, now: datetime = NOW) -> str:
    return (base_dir / "digests" / f"{now.date().isoformat()}.md").read_text(
        encoding="utf-8"
    )


def state_ids(base_dir: Path) -> list[str]:
    return sorted(e.id for e in load_state(base_dir / "state" / "published.json"))


def test_publishes_the_top_articles_and_the_state(
    inputs: Inputs, client: httpx.Client, tmp_path: Path
) -> None:
    provider = FakeProvider(ANSWERS)

    run(inputs, provider, client, tmp_path, NOW, force=False)

    digest = digest_text(tmp_path)
    titles = ["Published and updated", "Updated only, content only", "Rust 2.0 is out"]
    positions = [digest.index(f". {title}") for title in titles]
    assert positions == sorted(positions)
    assert "Plain post" not in digest
    assert "**Failed feeds:** Missing" in digest
    assert len(provider.calls) == 4
    assert state_ids(tmp_path) == sorted([BOTH, UPDATED, RUST])


def test_same_day_rerun_changes_nothing(
    inputs: Inputs, client: httpx.Client, tmp_path: Path
) -> None:
    run(inputs, FakeProvider(ANSWERS), client, tmp_path, NOW, force=False)
    state_path = tmp_path / "state" / "published.json"
    digest_before = digest_text(tmp_path)
    state_before = state_path.read_text(encoding="utf-8")
    provider = FakeProvider([])

    run(inputs, provider, client, tmp_path, NOW + timedelta(hours=2), force=False)

    assert provider.calls == []
    assert digest_text(tmp_path) == digest_before
    assert state_path.read_text(encoding="utf-8") == state_before


def test_force_regenerates_today_digest(
    inputs: Inputs, client: httpx.Client, tmp_path: Path
) -> None:
    run(inputs, FakeProvider(ANSWERS), client, tmp_path, NOW, force=False)
    # Today's articles are candidates again: plain now ranks first.
    provider = FakeProvider([answer(5), answer(9), answer(10), answer(7)])

    run(inputs, provider, client, tmp_path, NOW, force=True)

    assert len(provider.calls) == 4
    assert "## 1. Plain post" in digest_text(tmp_path)
    assert state_ids(tmp_path) == sorted([PLAIN, BOTH, UPDATED])


def test_next_day_excludes_articles_already_published(
    inputs: Inputs, client: httpx.Client, tmp_path: Path
) -> None:
    run(inputs, FakeProvider(ANSWERS), client, tmp_path, NOW, force=False)
    tomorrow = NOW + timedelta(days=1)
    provider = FakeProvider([answer(4)])

    run(inputs, provider, client, tmp_path, tomorrow, force=False)

    assert len(provider.calls) == 1
    assert "Plain post" in provider.calls[0][1]
    assert "## 1. Plain post" in digest_text(tmp_path, tomorrow)
    assert state_ids(tmp_path) == sorted([RUST, BOTH, PLAIN, UPDATED])


def test_no_candidate_still_writes_the_digest(
    inputs: Inputs, client: httpx.Client, tmp_path: Path
) -> None:
    later = NOW + timedelta(days=30)
    provider = FakeProvider([])

    run(inputs, provider, client, tmp_path, later, force=False)

    assert provider.calls == []
    digest = digest_text(tmp_path, later)
    assert "No new articles today." in digest
    assert "## Report" in digest
    assert state_ids(tmp_path) == []


def test_fatal_provider_error_writes_nothing(
    inputs: Inputs, client: httpx.Client, tmp_path: Path
) -> None:
    provider = FakeProvider([FatalProviderError("401 unauthorized")])

    with pytest.raises(FatalProviderError):
        run(inputs, provider, client, tmp_path, NOW, force=False)

    assert not (tmp_path / "digests").exists()
    assert not (tmp_path / "state").exists()


# main() runs in tmp_path and only covers paths that fail before any fetch or
# LLM call: no network, and the current date does not matter.


def test_invalid_input_exits_with_1_and_names_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    write_inputs(tmp_path, CONFIG_YAML.replace("top_n: 3", "top_n: 0"))
    monkeypatch.chdir(tmp_path)

    assert main([]) == 1
    assert "config.yaml: top_n" in caplog.text


def test_missing_api_key_exits_with_1_and_names_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    write_inputs(tmp_path, CONFIG_YAML.replace("provider: fake", "provider: mistral"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    assert main([]) == 1
    assert "MISTRAL_API_KEY is not set" in caplog.text
    assert not (tmp_path / "digests").exists()


def test_unknown_option_exits_with_2(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--unknown"])

    assert exit_info.value.code == 2


LABELS_CSV = (
    "url,title,description,score\nhttps://example.com/a,An article about Rust,,8\n"
)


def write_labels(base_dir: Path) -> None:
    (base_dir / "eval").mkdir()
    (base_dir / "eval" / "labels.csv").write_text(LABELS_CSV, encoding="utf-8")


def test_eval_prints_the_report_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    write_inputs(tmp_path)
    write_labels(tmp_path)
    monkeypatch.chdir(tmp_path)
    provider = FakeProvider([answer(7)])
    monkeypatch.setattr("auto_rss_sorting.cli.make_provider", lambda _: provider)

    assert main(["eval"]) == 0

    out = capsys.readouterr().out
    assert "    8    7    -1  An article about Rust" in out
    assert "accuracy: 1/1 within ±3 points (100 %), target 80 %: met" in out
    assert len(provider.calls) == 1
    assert not (tmp_path / "digests").exists()
    assert not (tmp_path / "state").exists()


def test_eval_without_labels_exits_with_1_and_names_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    write_inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "auto_rss_sorting.cli.make_provider", lambda _: FakeProvider([])
    )

    assert main(["eval"]) == 1
    assert "labels.csv: file not found" in caplog.text


def test_eval_missing_api_key_exits_with_1_and_names_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    write_inputs(tmp_path, CONFIG_YAML.replace("provider: fake", "provider: mistral"))
    write_labels(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    assert main(["eval"]) == 1
    assert "MISTRAL_API_KEY is not set" in caplog.text
