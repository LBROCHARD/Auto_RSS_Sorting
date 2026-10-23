# Phase 5: Digest and state

- **Status:** in progress
- **Branch:** `feature/digest-state` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Turn the scored articles into the day's digest `digests/YYYY-MM-DD.md` (top `top_n`, footer always present, "no new articles" case) and keep `state/published.json` up to date (exclusion of already published articles, purge, atomic write after the digest), with the same-day re-run rule and `--force`.

Out of this phase: wiring everything into the CLI, parsing the `--force` flag and computing "now" (phase 6). This phase provides tested functions that take `now` / `today`, the directories and a `force: bool` as parameters; phase 6 calls them in order. No new dependency: stdlib (`json`, `os`, `tempfile`) and `pydantic`.

## Design

Two new modules (`digest.py`, `state.py`) and one function added to `ranking.py`. Plain functions, no class hierarchy.

### Final ranking: `ranking.py`

- `top_articles(scored: list[tuple[Article, LLMScore]], top_n: int) -> list[tuple[Article, LLMScore]]`: sorts with the existing `ranking_key(llm_score.score, article)` (score desc, date desc, id), keeps the first `top_n`, or all of them if there are fewer. No threshold, no diversity rule. The tie-break rule stays in one place.

### `src/auto_rss_sorting/state.py`

- **`PublishedEntry`** (Pydantic, frozen, `extra="forbid"`): `id: NonEmptyStr`, `article_published_at: AwareDatetime`, `digest_date: date`.
- **File format:** a JSON list of entries, `article_published_at` in ISO 8601 UTC, `digest_date` as `YYYY-MM-DD`, sorted by `(digest_date, id)` and indented, so the committed file has small, stable diffs.
- **`load_state(path: Path) -> list[PublishedEntry]`**: a missing file is an empty state (first run). Unreadable file, invalid JSON or invalid entry → `StateError` naming the file and the problem (fail fast: a broken state would silently republish old articles).
- **`save_state(path: Path, entries: list[PublishedEntry]) -> None`**: atomic write through `write_atomic` (below).
- **`write_atomic(path: Path, text: str) -> None`**: writes to a temp file in the same directory (same filesystem, so the rename is atomic), flushes it, then `os.replace`. On any error the temp file is removed and the error is re-raised: the original file is left untouched. Creates the parent directory if missing. Shared by the state and the digest.
- **`purge(entries, now, max_age_days) -> list[PublishedEntry]`**: drops entries whose `article_published_at` is older than `now - max_age_days` (same cutoff as `collect_candidates`, so a purged article can never come back as a candidate).
- **`drop_digest_date(entries, today) -> list[PublishedEntry]`**: removes the entries of `today` (used by `--force`, so today's articles become candidates again).
- **`exclude_published(candidates: list[Article], entries) -> list[Article]`**: removes candidates whose id is in the state, keeping the input order. Called between `collect_candidates` and `prefilter`.
- **`add_published(entries, articles, today) -> list[PublishedEntry]`**: appends one entry per article of the digest.

### `src/auto_rss_sorting/digest.py`

- **`RunReport`** (frozen dataclass): `failed_feeds: list[str]`, `skipped_undated: int`, `skipped_invalid: int`, `skipped_transient: int`. Filled in phase 6 from `FetchResult` and `ScoringResult`.
- **`digest_path(digests_dir: Path, today: date) -> Path`**: `digests_dir / "YYYY-MM-DD.md"`.
- **`render_digest(today: date, ranked: list[tuple[Article, LLMScore]], report: RunReport) -> str`**: pure function, returns the Markdown. Format:

  ```markdown
  # Digest 2026-10-23

  ## 1. Rust 2.0 is out

  - **Source:** Lobsters
  - **Score:** 8/10
  - **Link:** <https://example.com/rust-2>

  **Summary:** ...

  **Reason:** ...

  ---

  ## Report

  - **Failed feeds:** none
  - **Skipped articles:** 3 without date, 1 invalid LLM response, 0 transient LLM error
  ```

  - no article: a "No new articles today." line instead of the list, footer still present;
  - failed feeds listed by name, `none` if empty;
  - article text and LLM output are untrusted data: the title is escaped for Markdown (`\`, `` ` ``, `*`, `_`, `[`, `]`, `<`, `>`, `#`) so it cannot break the heading or inject a link, and line breaks in the title, summary and reason are collapsed so they cannot create new headings or sections;
  - the link is the original `article.url` (always works), not the normalized id (removing a trailing slash can break some sites), between `<...>`.
- **`already_published(digests_dir: Path, today: date) -> bool`**: today's digest exists. Phase 6 calls it first and exits without changes unless `--force`.
- **`publish(digests_dir, state_path, today, ranked, report, entries) -> None`**: writes the digest (atomic), **then** the state with today's entries added (atomic). If the digest write fails, the state is not touched. With `--force`, the existing digest is simply overwritten.

### Order of a run (implemented in phase 6, given here so the pieces fit)

1. `already_published(...)` and not `force` → log and exit, nothing written.
2. `load_state` → `drop_digest_date` if `force` → `purge`.
3. fetch → `collect_candidates` → `exclude_published` → `prefilter` → `score_articles`.
4. `top_articles` → `render_digest` → `publish`.

## Steps

Each step is test-first (failing tests shown to you, then implementation) and ends with one commit.

- [ ] **1. `top_articles`.** Tests: sorted by LLM score desc; ties broken by date then id; same result whatever the input order; keeps `top_n`; fewer than `top_n` keeps them all; empty input gives empty output.
- [ ] **2. `render_digest`.** Tests: one article rendered with every field (rank, title, source, score, link, summary, reason); ranks follow the given order; footer with failed feeds listed and with `none`; skip counts in the footer; zero articles → "no new articles" message and footer; a title with Markdown characters is escaped; line breaks in the summary are collapsed.
- [ ] **3. State file: `PublishedEntry`, `load_state`, `save_state`, `write_atomic`.** Tests: missing file → empty state; round trip save → load; file written sorted by `(digest_date, id)`; invalid JSON and invalid entry (missing field, naive date) → `StateError` with the file name; atomic write: when the write fails (`os.replace` patched to raise), the original file is unchanged and no temp file is left.
- [ ] **4. State operations: `purge`, `drop_digest_date`, `exclude_published`, `add_published`.** Tests: entry older than `max_age_days` purged, entry exactly at the limit kept; `drop_digest_date` only removes today's entries; already published candidate excluded, the others kept in order; added entries carry the article id, its publication date and today's date.
- [ ] **5. `digest_path`, `already_published`, `publish`.** Tests (in `tmp_path`): digest file name is `YYYY-MM-DD.md`; `already_published` true / false; `publish` writes the digest and the state with today's entries; if the digest write fails, the state file is unchanged; same-day `--force` scenario: state with today's entries → `drop_digest_date` → `publish` again → the digest is overwritten and the state holds today's entries once, not twice.
- [ ] **6. Docs.** Tick this plan, mark the phase done in [PLAN.md](PLAN.md).

## Tests

- Files: `tests/test_ranking.py` (step 1, extended), `tests/test_digest.py` (steps 2 and 5), `tests/test_state.py` (steps 3 and 4).
- Articles and `LLMScore`s built inline with fixed dates, as in the existing tests. `today` and `now` are always given explicitly: no dependence on the current date.
- Files are written in pytest's `tmp_path` only, never in the real `digests/` or `state/`.
- The full same-day re-run (the CLI exits without changes) is tested end to end in phase 6, where the run order lives; this phase tests each piece it relies on.

## Decisions

- **Missing state file = empty state**, so the first run works without a committed empty file. A present but invalid file fails the run.
- **Purge cutoff identical to the candidate filter**, so purging an entry never lets its article come back.
- **The digest is also written atomically** (same helper as the state): cheap, and a half-written digest would otherwise block the same-day re-run.
- **If the state write fails after the digest is written**, the error propagates and the run fails; the digest stays. A re-run with `--force` repairs it. Not worth a rollback mechanism.
- **Zero candidates:** the digest is written with the "no new articles" message, and the state is still saved (the purge applies).
- **Link to `article.url`**, not the normalized id (see the digest format above).
- **Digest headings and labels in English**, like the rest of the code; summaries and reasons stay in the article's language (spec).

## Done when

- The digest format (footer, fewer than `top_n`, zero candidates) and every state case (exclusion, purge, atomic write, `--force`) are tested.
- `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` pass.
- `spec-reviewer` has reviewed the branch before merging into `dev`.
