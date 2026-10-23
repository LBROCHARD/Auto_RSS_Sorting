# Auto RSS Sorting

A daily digest of the 10 best articles from a list of RSS feeds, scored by an LLM against a description of my interests.

> Work in progress: v1 is under development. See [Docs/PLAN.md](Docs/PLAN.md) for the roadmap.

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
5. **Publish** the top `top_n` to `digests/YYYY-MM-DD.md`.

A GitHub Action runs it every day and commits the digest. The full specification is in [SPEC.md](SPEC.md).

## Configuration

| File | Content |
|---|---|
| `feeds.yaml` | Feeds to read (`name`, `url`) |
| `profile.md` | Description of the interests, read by the LLM |
| `keywords.yaml` | Weighted keywords for the pre-filter (e.g. `rust: 3`, `crypto: -5`) |
| `config.yaml` | Limits, LLM `provider` and `model`, model prices |

The LLM provider is selected in `config.yaml`. API keys are read from environment variables only.

## Usage

Requires Python 3.15 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync                        # install
uv run auto-rss-sorting        # generate today's digest
uv run auto-rss-sorting --force  # regenerate today's digest
uv run auto-rss-sorting eval   # measure the model against hand-scored articles
```

## Development

```sh
uv run pytest           # tests (no network, no LLM calls)
uv run ruff check .     # lint
uv run ruff format .    # format
```
