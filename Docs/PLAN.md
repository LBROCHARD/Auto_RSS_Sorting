# Auto RSS Sorting: global plan (v1)

Roadmap for implementing [SPEC.md](../SPEC.md). Each phase stays high level on purpose: a detailed plan (steps, tests, files) is written in `Docs/<feature-name>.md` right before the phase starts, and linked from its phase below.

## Current status

Phases 1 to 5 are merged into `dev`. Phase 6 is in progress on `feature/cli-pipeline`.

## How we work through phases

- Write a phase's detailed plan just before starting it, not all upfront: what we learn in phase N shapes phase N+1.
- One phase = one `feature/...` branch from `dev`, several small commits (one task = one commit), merged back into `dev`.
- Each phase has a clear "done when" criterion. Tick the phase here once it is merged.
- Before merging: tests, lint and format pass, and the `spec-reviewer` agent has reviewed the diff.

## Starting point

Project skeleton: `pyproject.toml` (no runtime dependencies), `src/auto_rss_sorting/__init__.py`, a smoke test, CI (lint + format + pytest), `feeds.yaml`, `profile.md`.

## Phases

The order follows the spec's pipeline, starting from the inputs, so each phase builds on tested pieces. The LLM comes late because everything before it is deterministic and easy to test.

### [x] Phase 1: Inputs and validation

Plan: [inputs-validation.md](inputs-validation.md) (done, merged in PR #2)

Pydantic models for `config.yaml`, `feeds.yaml`, `keywords.yaml`, check that `profile.md` exists. Fail fast with a clear message.
Dependencies to request: `pydantic`, `PyYAML`.

*Done when:* valid inputs load, and every invalid input has a test checking the failure and its message.

### [x] Phase 2: Feed fetching and candidates

Plan: [feed-fetching.md](feed-fetching.md) (done, merged into `dev`)

Fetch feeds (`httpx`, 10 s timeout), parse them (`feedparser`), normalize URLs, deduplicate, filter by `max_age_days` (injected "now"), exclude and count articles without a date, log and skip failing feeds. Tests use fixtures in `tests/fixtures/`, no network.
Dependencies to request: `httpx`, `feedparser`.

*Done when:* every feed edge case in the spec is covered (empty feed, 404, invalid XML, missing date, duplicate across feeds).

### [x] Phase 3: Keyword pre-filter and deterministic ranking

Plan: [keyword-prefilter.md](keyword-prefilter.md) (done, merged into `dev`)

Keyword score (whole word or phrase, case-insensitive), keep the `llm_max_articles` best, tie-break rule (score, date, URL) reusable for the final ranking.

Note: `keywords.yaml` contains keywords with non-word characters (`c++`, `post-mortem`) and accented French terms: a naive `` regex fails on `c++`, so whole-word matching must handle them.

*Done when:* ranking is tested as deterministic, ties included, and `rust` does not match "trust".

### [x] Phase 4: LLM layer

Plan: [llm-layer.md](llm-layer.md) (done, merged in PR #5)

Generic provider interface, one shared prompt (article text treated as data), Pydantic-validated response, retry rules (invalid response: 1 retry; transient error: 3 attempts with backoff; non-recoverable error: run fails). Fake provider for tests, then a first real adapter.
First adapter: Mistral's free tier, called with plain `httpx` (budget: at most 1 € per month). The comparison of providers is done in phase 7.

*Done when:* all retry/skip/fail behavior is tested with the fake provider, and the real adapter has been run once by hand.

### [x] Phase 5: Digest and state

Plan: [digest-state.md](digest-state.md) (done, merged in PR #6)

Generate `digests/YYYY-MM-DD.md` (ranking, footer, fewer than `top_n` articles, zero candidates), `state/published.json` (exclusion, purge, atomic write after the digest), same-day re-run and `--force`.

*Done when:* the digest format and every state case are tested.

### [ ] Phase 6: CLI and end-to-end pipeline

Plan: [cli-pipeline.md](cli-pipeline.md) (in progress)

Wire everything into the `auto-rss-sorting` command: "now" computed once at the entry point, logging, exit codes. End-to-end test with fixtures and the fake provider.

*Done when:* `uv run auto-rss-sorting` produces a real digest locally.

### [ ] Phase 7: `eval` subcommand

`eval/labels.csv` (20 hand-scored articles, provided by the project owner), accuracy (±3 points, target 80 %), cost per 100 articles, average latency.

Then a **provider benchmark**: run `eval` on 3 or 4 provider/model pairs (free tiers and cheap paid models, e.g. Claude Haiku 5.5), adding one adapter per new provider. Compare accuracy, cost per month at 50 articles/day, latency and the free tier's limits, then pick the production provider. Budget: at most 1 € per month.

*Done when:* `eval` prints the three metrics for the configured provider, the benchmark results are recorded in the phase plan, the production provider is chosen, and we know whether the success criterion is met.

### [ ] Phase 8: Scheduling and v1 release

Daily GitHub Actions workflow (cron + manual trigger, secrets), commit of the digest and state to `main`, README, merge `dev` into `main`.

*Done when:* a scheduled run has produced and committed a digest.

## Verification

- Every phase: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` pass, then `spec-reviewer` before merging.
- End of project: the spec's success criterion is measured with `eval`.
