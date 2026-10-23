# Phase 3: Keyword pre-filter and deterministic ranking

- **Status:** done, merged into `dev`
- **Branch:** `feature/keyword-prefilter` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Score each candidate with the weighted keywords of `keywords.yaml`, keep the `llm_max_articles` best, and provide the tie-break rule (score, then date, then URL) that the final ranking on the LLM score will reuse.

Out of this phase: the LLM score (phase 4), the final top `top_n` ranking and the digest (phase 5), wiring into the CLI (phase 6). No new dependency: everything uses the stdlib (`re`, `unicodedata`).

## Design

One module, plain functions, no class hierarchy.

### `src/auto_rss_sorting/ranking.py`

- `compile_keywords(keywords: dict[str, int]) -> list[KeywordPattern]`: compiled once per run. `KeywordPattern` is a frozen dataclass (`keyword`, `weight`, `pattern`). Patterns are compiled in `keywords.yaml` order.
- **Matching rule** (one regex per keyword, `re.IGNORECASE`, Unicode `\w`):
  - the keyword is escaped (`re.escape`), so `c++` or `retour d'expérience` are taken literally;
  - a boundary is required only on an edge where the keyword starts or ends with a word character: `(?<!\w)` before, `(?!\w)` after. So `rust` does not match "trust" nor "rusty", `post-mortem` does not match "post-mortems", and `c++` matches "C++" and "C++20" (it ends with `+`, no boundary needed on the right) but not "abc++";
  - whitespace inside a phrase matches any run of whitespace (`data center` matches "data\ncenter"), since descriptions come from HTML.
- **Text normalization** (applied to the keywords and to the text, so both sides compare the same way):
  - Unicode NFC, so an accent written as letter + combining mark matches the precomposed one in `keywords.yaml`;
  - typographic apostrophe `’` replaced by `'`, so `retour d'expérience` matches "retour d’expérience" (very common in French feeds).
- `keyword_score(article: Article, patterns: list[KeywordPattern]) -> int`: sum of the weights of the keywords found in `title + " " + description` (the space keeps the last word of the title and the first word of the description apart). Each keyword counts **once**, however many times it appears. Keywords are independent: a text containing "coding agent" gets both `coding agent` and `agent`.
- `ranking_key(score: int, article: Article) -> tuple`: `(-score, -published_at timestamp, id)`. The single place where the tie-break rule lives: score desc, then publication date desc, then normalized URL alphabetical. Used by the pre-filter now, and by the final ranking on the LLM score in phase 5.
- `prefilter(candidates: list[Article], patterns: list[KeywordPattern], limit: int) -> list[Article]`: sorts the candidates with `ranking_key(keyword_score(...), article)` and keeps the first `limit` (all of them if there are fewer). A negative score ranks an article lower but never excludes it. Logs at debug level the score of each kept article, and at info level how many were kept out of how many.

## Steps

Each step is test-first (failing tests shown to you, then implementation) and ends with one commit.

- [x] **1. Keyword matching and `keyword_score`.** Tests: `rust` matches "Rust" and "RUST" but not "trust" nor "rusty"; phrase (`data center`) matches, including across a line break; `c++` matches "C++" and "C++20", not "abc++"; `post-mortem` matches "Post-Mortem", not "post-mortems"; accented keyword (`énergie`) matches, including in decomposed form (NFD); `retour d'expérience` matches with a typographic apostrophe; keyword found in the title and in the description; title and description joined with a space (no match across them); a keyword repeated counts once; overlapping keywords (`coding agent` + `agent`) both count; negative weights are summed; no keyword found gives 0.
- [x] **2. `ranking_key` and `prefilter`.** Tests: sorted by score desc; equal score sorted by date desc; equal score and date sorted by id; same result whatever the input order (input given in two different orders); keeps exactly `limit` articles; fewer candidates than `limit` keeps them all; empty input gives empty output; a negative-score article is kept when there is room and ranked after the zero-score ones.
- [x] **3. Docs.** Tick this plan, mark the phase done in [PLAN.md](PLAN.md).

## Tests

- File: `tests/test_ranking.py`. Articles are built inline with a small helper (fixed dates, no fixture file needed: the pre-filter works on `Article`s, not on feeds).
- Keywords are given inline in the tests, not read from the real `keywords.yaml` (its weights will change over time).
- No dependence on the current date: only fixed `datetime`s.

## Decisions

- **Occurrences:** a keyword counts once per article, whatever the number of occurrences (the spec says "sum of the weights of keywords found").
- **Overlapping keywords:** each keyword is matched independently; `coding agent` and `agent` both count. Weights in `keywords.yaml` can be adjusted if this over-scores.
- **Boundaries:** required only on the edges of a keyword that are word characters, so keywords with symbols (`c++`) work.
- **Normalization:** NFC and typographic apostrophe only. No accent stripping (`energie` does not match "énergie"), no hyphen/space equivalence (`post-mortem` does not match "post mortem"): no stemming, as the spec says, and `keywords.yaml` lists the variants explicitly.
- **Tie-break:** one `ranking_key` function shared by the pre-filter and the final ranking, so the rule cannot drift between the two.

## Done when

- Ranking is tested as deterministic, ties included, and `rust` does not match "trust".
- `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` pass.
- `spec-reviewer` has reviewed the branch before merging into `dev`.
