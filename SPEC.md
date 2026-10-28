# Auto RSS Sorting: Specification (v1)

## Goal

Every day, read a list of RSS feeds, score articles against my interests, and publish a Markdown digest of the 10 best articles (title, score, link, summary, reason).

## Success criterion

On 30 articles that I scored by hand (`eval/labels.csv`, columns `url,title,description,score`), the LLM score is within **±3 points** of mine for at least **80 %** of them.
An `eval` subcommand runs the configured provider/model on this set and reports accuracy, cost per 100 articles and average latency, so providers can be compared by changing the config.

## Inputs

- `feeds.yaml`: list of feeds (`name`, `url`).
- `profile.md`: generic, non-personal description of my interests (read by the LLM, committed to the repo).
- `keywords.yaml`: weighted keywords for the local pre-filter (e.g. `rust: 3`, `crypto: -5`).
- `config.yaml`: `top_n` (10), `max_age_days` (7), `llm_max_articles` (50), `max_description_chars` (2000), `provider`, `model`,
  `price_input_per_mtok`, `price_output_per_mtok` (model prices per million tokens, used by `eval` to compute cost).
- All inputs (`config.yaml`, `feeds.yaml`, `keywords.yaml`, presence of `profile.md`) are validated at startup (fail fast with a clear message).
- Secrets (API keys) come only from environment variables / GitHub secrets.

## Pipeline

1. **Fetch** all feeds (10 s timeout each). A failing feed (timeout, 404, invalid XML) is skipped and logged.
2. **Collect candidates:** articles published within `max_age_days`, not already published in a previous digest (see State), deduplicated by normalized URL. Articles without a publication date are excluded and counted in the log.
3. **Pre-filter (local):** keyword score = sum of the weights of keywords found in title + description. Keep the `llm_max_articles` best.
4. **LLM scoring:** for each remaining article, the LLM receives `profile.md` + title + description (truncated to `max_description_chars`) and returns a score (0-10), a summary and a reason, in the article's language. Every candidate is re-scored on each run (no score cache).
5. **Rank:** sort by LLM score, keep the top `top_n`. No minimum threshold, no per-source diversity rule.
6. **Output:** write `digests/YYYY-MM-DD.md` and update the state. The CLI does not commit; the GitHub Action does (see Execution).

### Rules

- **Normalized URL** (article id and dedup key): lowercase scheme and host, tracking parameters removed (`utm_*`, `fbclid`, `gclid`), fragment and trailing slash removed.
- **Keyword matching:** whole word or phrase, case-insensitive, no stemming (`rust` does not match "trust"). Negative scores rank an article lower but never exclude it.
- **Tie-breaks** (pre-filter and final ranking): score (desc), then publication date (desc), then normalized URL (alphabetical). Output must be deterministic.
- **Time:** everything in UTC. Any function depending on "now" takes it as a parameter.

## LLM

- Provider-agnostic: a generic interface selected by `provider` and `model` in `config.yaml`, with one prompt shared by all providers. The code names no specific provider in logic; adding one means adding one adapter.
- Contract: `score(profile, article) -> {score: int 0-10, summary: str, reason: str}`, validated with Pydantic (integer in range, non-empty text).
- Article text is **data, not instructions**; the prompt says so explicitly.
- Invalid response for one article: one retry, then the article is skipped and logged.
- Transient errors (timeout, 429, 5xx): up to 3 attempts, exponential backoff (waits of 2 s then 4 s between attempts), then the article is skipped and logged.
- The two retry rules above use independent counters.
- Non-recoverable errors (401/403, quota exhausted) or no article could be scored: the run fails, no digest is produced.
- Cost note: up to 50 calls per day (no cache), so the chosen provider's daily limit must allow it.

## Digest

`digests/YYYY-MM-DD.md`. Per article: rank, title, source name, score /10, link, summary, reason.
Footer, always present: feeds that failed today, number of articles skipped (no date, invalid LLM response, transient LLM error).
Fewer than `top_n` candidates: publish them all. No candidate: still write the file with a "no new articles" message and the footer.

## State

- `state/published.json` (committed): `id` (normalized URL), `article_published_at`, `digest_date` per published article.
- Entries whose `article_published_at` is older than `max_age_days` are purged on each run.
- Written atomically (temp file + rename), only after the digest is written successfully.
- **Same-day re-run:** if `digests/YYYY-MM-DD.md` exists, exit without changes. `--force` removes today's entries from the state and regenerates.

## Execution

Python CLI `auto-rss-sorting` (with an `eval` subcommand), scheduled daily by GitHub Actions (cron + manual trigger). The Action commits the digest and the state directly to `main` (the feature-branch rule applies to development work only).

## Tests

pytest, LLM mocked with a fake provider, no network (fixture feeds), no dependence on the current date. Covers:
feed parsing (valid, empty, invalid XML, 404, missing date/description), URL normalization and dedup, keyword pre-filter, LLM response validation and retry/skip/fail behavior, deterministic ranking, state (purge, atomic write, exclusion), digest format (footer, fewer than 10, zero candidates), same-day re-run, input validation.

## Out of scope (v1)

Web interface, full-page download and text extraction (v1.1), score cache, user feedback, multiple users/profiles, notifications.