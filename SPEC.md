# Auto RSS Sorting — Specification

## Goal
Every day, read a list of RSS feeds, score articles against my interests, and publish a
Markdown digest of the 10 best articles (title, score, link, summary, reason).

## Inputs
- `feeds.yaml` — list of feeds, each with `name` and `url`.
- `profile.md` — free text describing my profile and interests (read by the LLM).
- `keywords.yaml` — weighted keywords used by the local pre-filter
  (e.g. `rust: 3`, `crypto: -5`).
- `config.yaml` — settings: `top_n` (10), `max_age_days` (7), `llm_max_articles` (50),
  LLM `provider` and `model`. Secrets (API keys) come from environment variables / GitHub secrets.

## Pipeline
1. **Fetch** all feeds. A failing feed (timeout, 404, invalid XML) is skipped and logged.
2. **Collect candidates**: articles published within `max_age_days`, excluding articles
   already published in a previous digest (see State). Articles seen but not published
   remain candidates.
3. **Pre-filter (local)**: compute a keyword score = sum of weights of keywords found in
   title + description. Keep the `llm_max_articles` best (~50).
4. **Content**: use RSS title + description; if the description is too short, download the
   page and extract the article text.
5. **LLM scoring**: for each remaining article, the LLM receives `profile.md` + article and
   returns a score (0–10), a summary and a reason, written in the article's language.
   Every candidate is re-scored on each run (no score cache).
6. **Rank**: sort by LLM score, keep the top 10 (always 10 if at least 10 candidates exist,
   no minimum threshold, no per-source diversity rule).
7. **Output**: write `digests/YYYY-MM-DD.md`, update the state, commit both.

## LLM
- Generic provider interface; the provider and model are selected in `config.yaml`,
  so several APIs can be compared by changing the config.
- On API failure: a few retries, then the run fails (no digest produced).

## Digest format
One Markdown file per day. For each article: rank, title, source name, score /10, link,
summary, reason it may interest me.

## State
- `state/published.json` (committed): articles already published in a digest
  (id = article URL/GUID, publication date).
- Entries older than `max_age_days` are purged on each run.

## Execution
- Python CLI `auto-rss-sorting`.
- Scheduled once a day via GitHub Actions (cron); the Action commits the digest and state.

## Tests
Unit tests with pytest: feed parsing, keyword pre-filter, ranking, state handling;
the LLM is mocked.

## Out of scope (v1)
- Web interface
- User feedback (like/dislike) to learn the profile
- Multiple users / profiles
- Notifications (email, Slack, …) — maybe later
