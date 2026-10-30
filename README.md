# Auto RSS Sorting

A daily digest of the 10 best articles from a list of RSS feeds, scored by an LLM against a description of my interests.

v1 is released: a GitHub Action publishes a new digest every morning in [`digests/`](https://github.com/LBROCHARD/Auto_RSS_Sorting/tree/main/digests) on `main`.

## Why this project

This is first a learning project: I am building it to practice AI-assisted development, trying out tools and workflows (Claude Code, spec refined through "grilling" sessions, phase plans, a reviewer agent...) to code as efficiently as possible.

The process is part of the repo:

- [JOURNAL.md](JOURNAL.md): what I learned, and a log of each task (time estimated without AI, actual time with AI, AI mistakes).
- [CLAUDE.md](CLAUDE.md): the rules the AI follows on this project.
- [SPEC.md](SPEC.md) and [Docs/](Docs/): the specification and the plan of each phase.

## How it works

1. **Fetch** every feed in `feeds.yaml` (failing feeds are logged and skipped).
2. **Collect** recent articles (`max_age_days`), deduplicated and not already published.
3. **Pre-filter** locally with weighted keywords from `keywords.yaml`, keeping the best `llm_max_articles`.
4. **Score** each remaining article with an LLM (0-10, summary, reason) against `profile.md`.
5. **Publish** the top `top_n` to `digests/YYYY-MM-DD.md`, and record the published articles in `state/published.json` so they are not published again.

The full specification is in [SPEC.md](SPEC.md).

## Example output

Two digests and the matching state, produced by local runs before the release and kept as a frozen sample. They are unedited model output, quirks included (a reason that does not quite fit its article, two entries about the same story):

- [`examples/digests/2026-10-29.md`](examples/digests/2026-10-29.md): a digest with the final prompt (rank, title, source, score, link, summary and reason in the article's language, footer with failed feeds and skipped articles).
- [`examples/digests/2026-10-28.md`](examples/digests/2026-10-28.md): the previous day's digest.
- [`examples/state/published.json`](examples/state/published.json): the state after these two runs (one entry per published article: normalized URL, publication date, digest date).

The live digests and state are in `digests/` and `state/` on the `main` branch.

## Choosing the LLM: evaluation and benchmark

The LLM score is the whole product: if it does not match my judgement, the digest is useless. So the spec sets a measurable success criterion: on 40 articles I scored by hand ([`eval/labels.csv`](eval/labels.csv)), the LLM score must be within **±3 points** of mine for at least **80 %** of them.

`uv run auto-rss-sorting eval` runs the configured provider and model on this set, with the exact production prompt, and reports accuracy, cost per 100 articles and average latency. Changing `provider` and `model` in `config.yaml` is enough to compare models on the same ground.

Benchmark of free tiers (October 2026):

| Provider / model | Accuracy (±3) | Avg latency | Notes |
|---|---|---|---|
| **gemini / gemini-3.5-flash-lite** | **36/40 (90 %)** | 0.82 s | **chosen**: most accurate, fastest, 500 requests/day free |
| mistral / ministral-14b-2512 | 33/40 (82 %) | 2.34 s | always over-scores generic AI content |
| mistral / ministral-8b-2512 | 32/40 (80 %) | 1.77 s | also under-scores two relevant articles |
| mistral / mistral-small-2603 | run failed | - | every call rate-limited on the free tier |

Beyond picking a model, the eval caught real problems a unit test could not: malformed JSON answers that silently dropped 6 relevant articles (fixed with the provider's JSON mode), a free tier that was unusable in practice, and summaries written in the wrong language (fixed with a stricter prompt rule, checked again with `eval`). Every run is detailed in [Docs/eval.md](Docs/eval.md).

## Configuration

| File | Content |
|---|---|
| `feeds.yaml` | Feeds to read (`name`, `url`) |
| `profile.md` | Description of the interests, read by the LLM |
| `keywords.yaml` | Weighted keywords for the pre-filter (e.g. `rust: 3`, `crypto: -5`) |
| `config.yaml` | Limits, LLM `provider` and `model`, model prices |

The LLM provider is selected in `config.yaml` (`gemini` or `mistral`). API keys are read from environment variables only: `GEMINI_API_KEY` or `MISTRAL_API_KEY`.

## Usage

Requires Python 3.15 and [uv](https://docs.astral.sh/uv/). Set the API key of the configured provider in your environment first.

```sh
uv sync                          # install
uv run auto-rss-sorting          # generate today's digest
uv run auto-rss-sorting --force  # regenerate today's digest
uv run auto-rss-sorting eval     # measure the model against hand-scored articles
```

## Daily run on GitHub Actions

[`.github/workflows/daily.yml`](.github/workflows/daily.yml) runs the pipeline every day at 05:00 UTC and commits the digest and the state to `main`.

- **Branches:** `dev` is the default branch, where development happens and where the workflow file lives (GitHub only schedules workflows from the default branch). `main` holds the releases and the daily commits: the workflow checks out `main`, runs the released code and pushes back to `main`.
- **Setup on a fork:** add a `GEMINI_API_KEY` repository secret (Settings → Secrets and variables → Actions), and enable Actions on the fork.
- **Manual run:** Actions tab → "Daily digest" → "Run workflow". Tick `force` to regenerate today's digest; without it, a second run on the same day changes nothing.
- **After 60 days without activity** on the repository, GitHub disables scheduled workflows. Re-enable it from the Actions tab ("Daily digest" → "Enable workflow").

## Development

```sh
uv run pytest           # tests (no network, no LLM calls)
uv run ruff check .     # lint
uv run ruff format .    # format
```
