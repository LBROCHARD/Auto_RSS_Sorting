# Phase 2: Feed fetching and candidates

- **Status:** in progress
- **Branch:** `feature/feed-fetching` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Fetch every feed of `feeds.yaml`, parse it into articles, and turn them into the candidate list: articles within `max_age_days`, deduplicated by normalized URL. A failing feed is logged and skipped; articles without a date are excluded and counted.

Out of this phase: exclusion of articles already published (needs the state, phase 5), keyword pre-filter and ranking (phase 3), truncation to `max_description_chars` (phase 4, it only matters for the prompt), wiring into the CLI and creating the real HTTP client at the entry point (phase 6).

## Design

Two modules, plain functions, no class hierarchy.

### `src/auto_rss_sorting/feeds.py`: fetch and parse

- `Article`: frozen dataclass with `id` (normalized URL), `url` (link as given by the feed, shown in the digest), `title`, `description` (plain text), `published_at` (aware `datetime`, UTC), `source` (feed name).
- `FeedError(Exception)`: one feed could not be fetched or parsed. Message names the feed and the reason. Never escapes `fetch_all`.
- `make_http_client() -> httpx.Client`: 10 s timeout (`FEED_TIMEOUT_SECONDS = 10`), `follow_redirects=True` (httpx does not follow them by default), an explicit `User-Agent`. Called by the CLI in phase 6; tests build their own client on `httpx.MockTransport`.
- `fetch_feed(client, feed) -> bytes`: GET, `raise_for_status()`. `httpx.HTTPError` (timeout, connection error, 4xx/5xx) becomes `FeedError`. Returns raw bytes so feedparser handles the encoding.
- `parse_feed(feed, content) -> ParsedFeed`: `ParsedFeed` holds `articles` and `undated_count`.
  - Invalid XML: `FeedError` only when feedparser reports an error (`bozo`) **and** extracted no entry. Bozo with entries: keep them, log a warning.
  - Empty feed (valid, zero entries): not an error, zero articles.
  - Date: `published`, else `updated`, converted to UTC. Neither: entry excluded and counted in `undated_count`.
  - Description: `summary`, else the first `content` value, else `""`; converted to plain text.
  - Missing title: `""`. Missing link: entry skipped and logged (no id possible).
- `fetch_all(client, feeds) -> FetchResult`: sequential, in `feeds.yaml` order. `FetchResult` holds `articles` (in feed order), `failed_feeds` (names, for the digest footer), `undated_count` (total). Each failure is logged with the feed name and the reason, then skipped.
- `html_to_text(html) -> str`: stdlib `html.parser` (no dependency), entities unescaped, whitespace collapsed. Text inside `<script>`/`<style>` is dropped.

### `src/auto_rss_sorting/candidates.py`: normalize, filter, dedup

- `normalize_url(url) -> str`: lowercase scheme and host; remove `utm_*`, `fbclid`, `gclid` from the query (other parameters kept in their order); remove the fragment and the trailing slash (`https://a.com/` -> `https://a.com`). Nothing else (no port or `www.` handling: not in the spec). Used by `parse_feed` to build `Article.id`, and later by the state (phase 5).
- `collect_candidates(articles, now, max_age_days) -> list[Article]`:
  - keeps articles with `published_at >= now - max_age_days` (boundary included). Articles dated in the future are kept (clock skew between servers).
  - deduplicates by `id`: the first occurrence wins, so the feed listed first in `feeds.yaml` gives the source name.
  - keeps the input order; ranking is phase 3.
  - `now` is a parameter, never `datetime.now()`.

## Steps

Each step is test-first (failing tests shown to you, then implementation) and ends with one commit.

- [x] **1. Dependencies.** Ask approval, then `uv add httpx feedparser`. Check they install on Python 3.15 (feedparser pulls `feedparser-sgmllib`, pure Python).
- [x] **2. `normalize_url`.** Tests: lowercase scheme/host but not path; each tracking parameter removed (`utm_source`, `utm_medium`, `fbclid`, `gclid`); other parameters kept in order; fragment removed; trailing slash removed (root and path); already-normalized URL unchanged; two variants of one URL give the same id.
- [ ] **3. `html_to_text`.** Tests: tags removed; entities unescaped (`&amp;`, `&eacute;`); whitespace collapsed; `<script>` content dropped; plain text unchanged; empty string.
- [ ] **4. `parse_feed`.** Fixtures in `tests/fixtures/`: valid RSS 2.0, valid Atom (one entry with `updated` only), empty feed, invalid XML, entry without any date, entry without description, entry with HTML description, entry without link. Tests: fields extracted; dates in UTC (non-UTC offset in a fixture); `updated` fallback; undated entry excluded and counted; empty feed gives zero articles; invalid XML raises `FeedError`; bozo with entries keeps them.
- [ ] **5. `fetch_feed` / `fetch_all`.** `httpx.MockTransport` serving the fixtures. Tests: 200 returns articles; 404, 500, timeout and connection error each skip the feed and list it in `failed_feeds`; invalid XML through `fetch_all` is skipped too; one failing feed does not stop the others; redirect is followed; `undated_count` summed across feeds; failure logged with the feed name (`caplog`); `make_http_client` has a 10 s timeout.
- [ ] **6. `collect_candidates`.** Tests (fixed `now`): article older than `max_age_days` excluded; exactly on the boundary kept; future date kept; duplicate across two feeds kept once with the first feed's source; duplicate URL variants (tracking params, trailing slash) deduplicated; order preserved; empty input gives empty output.
- [ ] **7. Docs.** Tick this plan, mark the phase done in [PLAN.md](PLAN.md).

## Tests

- Files: `tests/test_feeds.py`, `tests/test_candidates.py`, fixtures in `tests/fixtures/` (small hand-written XML files, a few entries each, fixed dates).
- No network: every HTTP call goes through `httpx.MockTransport`.
- No dependence on the current date: `now` is a fixed `datetime` in tests, and fixtures use fixed dates.
- `normalize_url` and `html_to_text` are tested on inline strings (easier to read next to the assertion).

## Decisions

- **Date:** `published`, else `updated`. Only entries with neither are excluded and counted (many Atom feeds only have `updated`).
- **Duplicates across feeds:** first occurrence in `feeds.yaml` order wins.
- **Invalid XML:** a feed fails only if feedparser reports an error and extracted nothing; otherwise its entries are kept and a warning is logged.
- **HTML in descriptions:** converted to plain text in this phase, with the stdlib (for the keyword matching in phase 3 and the prompt in phase 4).
- **Already published articles:** excluded in phase 5, together with reading the state.
- **Fetching:** sequential. Worst case about 27 x 10 s, fine for a daily job.

## Done when

- Every feed edge case of the spec is tested: empty feed, 404, invalid XML, missing date, missing description, duplicate across feeds.
- `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` pass.
- `spec-reviewer` has reviewed the branch before merging into `dev`.
