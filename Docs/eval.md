# Phase 7: `eval` subcommand and provider benchmark

- **Status:** in progress
- **Branch:** `feature/eval` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Measure the spec's success criterion: on the 40 hand-scored articles of `eval/labels.csv`, the LLM score is within ±3 points of the owner's score for at least 80 % of them. An `auto-rss-sorting eval` subcommand runs the configured provider/model on this set and prints accuracy, cost per 100 articles and average latency. Then benchmark 3 or 4 provider/model pairs with it, pick the production provider (budget: at most 1 € per month) and record the results here.

Out of this phase: the GitHub Actions workflow and the README (phase 8). No score cache, no new dependency: `csv` from the stdlib, `pydantic`, `httpx` for new adapters.

## Design

One new module, `src/auto_rss_sorting/evaluation.py`, and a subcommand in `cli.py`. Plain functions, as in the previous phases.

### `eval/labels.csv` (provided by the project owner)

- Columns `url,title,description,score` (spec), UTF-8, standard CSV quoting (a description containing a comma is quoted).
- 40 rows (the spec first said 20), scored by hand **before** looking at any LLM output. To make the measure meaningful: a spread of scores (some low, some mid, some high), a mix of French and English articles, descriptions copied as the feeds give them and cut at 2000 characters, exactly as the prompt truncates them (`max_description_chars`).
- Committed: the articles are public and the scores say nothing personal beyond `profile.md`.

### `evaluation.py`

- **`Label`** (Pydantic, frozen, extra fields forbidden): `url: HttpUrl`, `title: NonEmptyStr`, `description: str` (may be empty, like a feed), `score: int` in `0..10`.
- **`load_labels(path: Path) -> list[Label]`**: fail fast with `InputError` and a message naming the file and the row: file missing, wrong header, invalid row (bad URL, score not an integer or out of range, empty title), no rows, duplicate URL (after normalization, with the existing `normalize_url`).
- **`label_to_article(label) -> Article`**: the label becomes an `Article` so the **exact production prompt** is used (`build_prompt` via `score_article`). `source` is the URL's host (the CSV has no source column), `published_at` is a fixed placeholder (the prompt does not use it).
- **`evaluate(provider, profile, labels, max_description_chars, sleep) -> EvalReport`**: scores each label with `score_article` (same retry rules as production: one retry on invalid response, 3 attempts on transient errors). A `MeteredProvider` wrapper around the provider adds up the token usage and latency of **every** call, retries included (they are real costs).
  - `EvalReport` (frozen dataclass): per-article `results` (label, LLM score or skip reason), `input_tokens`, `output_tokens`, `calls` (completed calls), `total_latency_seconds`; derived `within_tolerance`, `accuracy`, `average_latency_seconds`, and `cost_per_100_articles(price_input_per_mtok, price_output_per_mtok)` (prices passed in, so `evaluate` does not need the config).
  - **Accuracy** = articles with `|llm - human| <= 3` / number of labels. A skipped article counts as a miss: the criterion is about all the labelled articles, not only the ones that could be scored.
  - **Cost per 100 articles** = `(input_tokens × price_input_per_mtok + output_tokens × price_output_per_mtok) / 1,000,000 / number of labels × 100`.
  - **Average latency** = total latency / number of calls.
  - `FatalProviderError` propagates (eval fails). If no article could be scored: `ScoringFailedError`, as in a daily run.
- **Latency measurement:** the Mistral adapter waits up to 2 s before a call (free-tier pacing). Timing `complete()` from outside would count that wait as latency and penalize paced providers unfairly. So `Completion` gets a `latency_seconds: float` field, measured by the adapter around the HTTP request only, with its already injected clock. `FakeProvider` returns a fixed value.
- **`format_report(report, config) -> str`**: plain text printed on stdout (the command's result; logs stay on stderr):

  ```
  eval: mistral / ministral-14b-2512, 40 articles
  human  llm  diff  title
      8    7    -1  Rust 2.0 is out
      2    -      -  Some article (skipped: invalid LLM response)
  ...
  accuracy: 34/40 within ±3 points (85 %), target 80 %: met
  cost: 0.0000 per 100 articles (24,180 input tokens, 2,310 output tokens)
  latency: 0.84 s per call on average (21 calls)
  ```

  Per-article lines make it possible to see *where* the model disagrees, which is what we need to compare models or adjust the prompt. Rows are listed in CSV order (deterministic).

### CLI: `auto-rss-sorting eval`

- `argparse` subparser `eval`, no option. `auto-rss-sorting` without a subcommand keeps today's behavior (daily run, `--force`).
- Same startup as a run: `load_inputs` (all inputs validated, spec), `make_provider` (fail fast on missing key), then `load_labels(base_dir / "eval/labels.csv")`.
- Fetches no feed, writes no digest, never touches the state.
- Exit codes: `0` when the report is printed (whether or not the 80 % target is met: eval measures, it does not gate anything); `1` for the expected failures (invalid inputs or labels, fatal provider error, nothing scored), same one-line error as a run.

## Steps

Each code step is test-first (failing tests shown to you, then implementation) and ends with one commit.

- [x] **0. Plan.** This file, plus the pending PLAN.md / `cli-pipeline.md` updates marking phase 6 merged. One `:memo:` commit on `feature/eval`.
- [x] **1. `load_labels`.** Tests with small CSV files written inline in `tmp_path` (as in `test_inputs.py`): valid file; missing file; wrong header; score `11`, `-1`, `7.5`, `abc`; empty title; invalid URL; empty file (header only); duplicate URL (same after normalization). Each error message names the file and the row.
- [x] **2. Latency in `Completion`.** The Mistral adapter measures the HTTP request only, not the pacing wait (test with the injected clock: a paced call reports the request time, not the wait). `FakeProvider` updated.
- [x] **3. `evaluate` and `EvalReport`.** Tests with `FakeProvider`: diff of exactly 3 counts as within, 4 does not (both directions); a skipped article counts as a miss; cost computed from the tokens of every call, retries included; average latency over all calls; prices at 0 → cost 0; fatal error propagates; nothing scored → `ScoringFailedError`; the prompt sent is the production prompt (title, host as source, description truncated).
- [x] **4. `format_report` and the `eval` subcommand.** Tests: report text for a small fixed `EvalReport` (target met / not met, skipped row); `main(["eval"])` with a missing `eval/labels.csv` → exit 1 and a message naming the file; missing API key → exit 1; `main([])` still runs the daily pipeline path (existing tests stay green).
- [x] **5. Labels.** You write `eval/labels.csv` (40 rows, see above). I validate it by running `load_labels` on it, without calling any LLM. Committed with step 6's results or on its own.
- [x] **6. First eval: current provider.** You run `uv run auto-rss-sorting eval` with your `MISTRAL_API_KEY` (I never read `.env` nor pass a key on a command line). We record the three metrics here. The language drift seen in phase 4 is checked in step 9 instead (see Decisions).
- [x] **6b. Fix the malformed answers.** Run 1 lost 6 articles to malformed JSON: the Mistral adapter now requests JSON mode (`response_format: {"type": "json_object"}`, checked in the official API docs). Test: the request body holds it. Then run eval again (run 2).
- [x] **7. Benchmark, same adapter.** Other Mistral models need only a `config.yaml` change: `mistral-small-2603` and `ministral-8b-2512` (see the limits recorded in [llm-layer.md](llm-layer.md)). Run eval for each, record the results.
- [x] **8. Benchmark, new adapter(s).** Plain `httpx`, same error mapping and security rules as the Mistral adapter, tests with `httpx.MockTransport`, then one eval run per provider. Decided with the project owner: free tiers only, plus Claude Haiku 5.5 (the only paid candidate, cheap). Exact API details and prices are checked in the provider's official docs at the start of each sub-step, not from memory.
  - [x] **8a. One adapter for every OpenAI-style chat completions API** (refactor, no behavior change). `MistralProvider` becomes `ChatCompletionsProvider`, built from a small per-provider description (`ChatAPI`: name for error messages, fixed URL, minimum interval between calls, provider-only request fields). Mistral is the first entry. Existing tests are renamed, not weakened. Why: Gemini (and other free tiers) accept the same request and response format, so a second copy of the adapter would duplicate everything.
  - [x] **8b. Gemini** (`provider: gemini`, `GEMINI_API_KEY`, model `gemini-3.5-flash-lite`). Free tier re-checked during phase 7 (see Decisions); OpenAI-compatible endpoint `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`, key in the `Authorization: Bearer` header. Gemini 3 models always "think" before answering: the request sets `reasoning_effort: "low"` so the thinking does not eat the 500-token answer budget. Limits read in the project owner's AI Studio console (2026-10-29) for Gemini 3.5 Flash-Lite: 15 requests/min, 250,000 input tokens/min, 500 requests/day; hence 4 s between calls. A daily run uses at most 150 requests (50 articles, retries included) and an eval run about 40, so several eval runs a day still fit. Error mapping checked in the official API errors page: 401 (invalid key), 403 (no access) and 404 (unknown model) are fatal, 429 (rate limit or daily quota) and 5xx transient, as for Mistral. Then eval run.
  - [x] ~~**8c. Anthropic**~~ **Skipped** (project owner's decision after run 5): Gemini met the target with margin for free, so a paid model could only win on accuracy, at a cost. Claude Haiku 5.5 stays an option if the free tier changes.
- [ ] **9. Decision.** Fill the benchmark table, pick the production provider, set it in `config.yaml` (provider, model, prices). If no pair reaches 80 %, we discuss before changing anything (prompt wording, model, or the labels themselves). Then check the summary language of the chosen model on a real digest (`--force`, not committed), and decide whether the prompt needs a stronger language rule.
- [ ] **10. Docs.** Tick this plan, mark the phase done in [PLAN.md](PLAN.md).

## Tests

- New file `tests/test_evaluation.py`; additions to `tests/test_cli.py` and `tests/test_providers.py` (latency, new adapters).
- LLM never called (`FakeProvider`), no network (`httpx.MockTransport` for adapters), no dependency on the current date (eval does not read the clock for dates; latency uses the injected monotonic clock).
- CSV files are written inline in `tmp_path`, as in `test_inputs.py`, and stay tiny (2-3 rows): what matters is each validation case, not volume.
- Retry/skip rules are already tested in phase 4: only their effect on eval metrics is tested here.

## Benchmark results

To fill in steps 6 to 9. Monthly cost = cost per 100 articles × 15 (50 articles/day × 30 days).

| Provider / model | Accuracy (±3) | Cost / 100 articles | Cost / month | Avg latency | Free tier limits | Notes |
|---|---|---|---|---|---|---|
| mistral / ministral-14b-2512 | 33/40 (82 %) | 0 | 0 | 2.34 s (40 calls) | 937,500 tok/min, 0.5 req/s | current; run 2, JSON mode: 0 skipped, 7 misses all over-scored (+4 to +7). Run 1 without JSON mode: 28/40 (70 %) |
| mistral / mistral-small-2603 | 0/40, run failed | 0 | 0 | - | 20,000 tok/min | run 3: every call answered 429, all 40 articles skipped. Unusable on this account's free tier |
| mistral / ministral-8b-2512 | 32/40 (80 %) | 0 | 0 | 1.77 s (40 calls) | 625,000 tok/min, 3.13 req/s | run 4, JSON mode: 0 skipped, 8 misses: 6 over-scored (+4 to +8), 2 under-scored (-4) |
| gemini / gemini-3.5-flash-lite | 36/40 (90 %) | 0 | 0 | 0.77 s (41 calls) | 15 req/min, 250,000 input tok/min, 500 req/day | run 5: 0 skipped, 1 retry, 4 misses all over-scored (+4 to +8), no under-scoring beyond -2 |
| anthropic / Claude Haiku 5.5 | not run | | | | paid, no free tier | skipped: Gemini met the target for free (step 8c) |

### Run 1: mistral / ministral-14b-2512 (2026-10-28)

- 28/40 within ±3 (70 %): target not met. 44,037 input and 6,811 output tokens, about 1,100 input tokens per article.
- **6 articles skipped** after two invalid responses (12 of the 46 calls): The October inflection point for vibe game development, This Week in Rust 674, Announcing Rust 1.99.1, Graphics Programming weekly 456, Tokens and Greens, SCI for AI Bootcamp. All were scored 6 to 9 by hand, so in production they are relevant articles silently missing from the digest. Cause, from the run's warnings: **malformed JSON**, not a truncated answer. Every invalid answer is complete (it ends with `"\n}`) but fails with `expected ',' or '}'` at the start of a line (column 3), i.e. a missing comma between two values. The model gave 7 or 9 to all six: its enthusiastic answers are the malformed ones. The retry never helps: with `temperature: 0`, the same request returns the same malformed answer.
- **6 misses among the 34 scored, all over-scored:** a video course on reasoning models (1 → 8), SIMD (0 → 7), GitHub Copilot for beginners (2 → 8), Anthropic coding interviews (4 → 8), Retell / OpenAI (3 → 7), Apple JSON in Xcode (3 → 7). The model rates generic AI and developer content too high.
- With the skipped articles scored correctly, the result would be at most 34/40 (85 %): fixing the invalid responses matters more than the model choice.

### Run 2: mistral / ministral-14b-2512, JSON mode (2026-10-29)

- **33/40 within ±3 (82.5 %, printed 82 %): target met**, by a small margin (32/40 is exactly 80 %, so one more miss still passes, two fail). 37,245 input and 5,216 output tokens, about 930 input tokens per article.
- **JSON mode fixed the invalid responses:** 0 skipped, 40 calls for 40 articles (no retry at all). Of the 6 articles lost in run 1, 5 are now within tolerance; This Week in Rust 674 is over-scored (4 → 9).
- **7 misses, all over-scored:** the 6 of run 1 (reasoning-model course 1 → 8, SIMD 0 → 7, Copilot for beginners 2 → 8, Anthropic interviews 4 → 8, Retell 3 → 7, Apple JSON in Xcode 3 → 7) plus This Week in Rust 674. No article is under-scored by more than 3: the model is too generous with AI and developer content, but never misses a relevant article.
- The off-topic articles (crypto, politics, mainstream games, food) are all scored 0-2, as by hand.

### Run 3: mistral / mistral-small-2603 (2026-10-29)

- **Run failed: none of the 40 articles could be scored.** Every call answered `429 Rate limit exceeded` (`"type":"rate_limited","code":"1300"`), including the retries after 2 s and 4 s. Each article was skipped after its 3 attempts, then the run failed as the spec requires.
- The 429s lasted the whole run (about 6 minutes, 120 calls). A per-minute token limit would have let calls through again within a minute. The model is most likely not usable at all on this account's free tier (zero or exhausted quota): not a pacing problem the code can fix.
- The error handling worked as designed: transient errors retried with backoff, each article skipped and logged, no digest from a run where nothing was scored.
- Result: mistral-small-2603 is out of the benchmark.

### Run 4: mistral / ministral-8b-2512, JSON mode (2026-10-29)

- **32/40 within ±3 (80 %): target met, with no margin** (one more miss fails). 37,245 input and 4,985 output tokens, 0 skipped, 40 calls (no retry), 1.77 s per call on average (ministral-14b: 2.34 s).
- **6 over-scored misses**, mostly the same as ministral-14b: reasoning-model course 1 → 9, SIMD 0 → 7, Copilot for beginners 2 → 7, This Week in Rust 674 4 → 9, Retell 3 → 7, Apple JSON in Xcode 3 → 7.
- **2 under-scored misses**, which ministral-14b never had: Artificial Analysis v5 6 → 2 and Announcing Rust 1.99.1 6 → 2. Under-scoring is the costly error for a digest: a relevant article drops out instead of a weak one getting in.
- The off-topic articles are all scored 0, as by hand.
- Compared with ministral-14b (82 %, no under-scoring), ministral-8b is slightly faster but less accurate, and both are free: ministral-14b stays the best Mistral candidate.

### Run 5: gemini / gemini-3.5-flash-lite, JSON mode, `reasoning_effort: low` (2026-10-29)

- **36/40 within ±3 (90 %): target met with margin** (four more misses still pass). 39,183 input and 3,463 output tokens, 0 skipped, 41 calls for 40 articles (one retry, which succeeded; no warning, since only skipped articles are logged), 0.77 s per call on average: about 3 times faster than ministral-14b, even with thinking on.
- JSON mode and `reasoning_effort` are both accepted by the OpenAI-compatible endpoint (no 400), and no answer was truncated by the thinking.
- **4 misses, all over-scored:** reasoning-model course 1 → 9, SIMD 0 → 6, This Week in Rust 674 4 → 8, Apple JSON in Xcode 3 → 8. The first three are missed by every model so far: they may say more about the labels or `profile.md` than about the models.
- No article is under-scored by more than 2. Gemini fixes two misses shared by both Mistral models: Copilot for beginners (2 → 2) and Retell (3 → 6, within tolerance).
- **Bias to watch:** Gemini scores high generously. 6 articles sit exactly at +3, just inside the tolerance, and 6 articles get 10 against 1 by hand. The ranking still works (the digest keeps the top 10), but many ties at 10 would be broken by date, not by relevance.
- The off-topic articles are scored 0-3, as by hand (0-2).

### Language check: real digest with Gemini (step 9, digest of 2026-10-29, `--force`, not committed)

- 10 articles, 0 skipped. 18 of the 20 texts (summary + reason) are in the article's language, against 1 of 10 English articles summarized in English by `ministral-14b-2512` in phase 6.
- 2 drifts: the English article "Gemini 4 Carbon: Our next frontier model" (Google DeepMind) got a French summary and a French reason; the French article "Mistral lance la version finale de Large 4" got a French summary but an English reason.
- The drift is small but the spec asks for the article's language in both fields.

## Decisions

- **Same prompt and retry rules as production.** Eval measures what the daily run will actually do; a separate eval prompt would measure something else.
- **Skipped article = miss.** The spec counts on all the labelled articles; ignoring skips would reward an unreliable provider.
- **Retries count in cost and latency.** They are paid and waited for in production too.
- **Latency measured by the adapter** around the HTTP request, so a provider's free-tier pacing does not count as latency (see Design).
- **No currency in the code.** Prices in `config.yaml` are in the provider's billing currency; the benchmark table converts to euros by hand for the 1 € budget.
- **Eval exit code is 0 even below 80 %.** It is a measuring tool, not a gate; the report says whether the target is met.
- **`source` = URL host** for eval articles: the CSV has no source column (spec), and the prompt expects one.
- **No mean absolute error in the report.** Not in the spec; the per-article lines already show how far each score is. The labels must cover the whole 0-10 range, otherwise the ±3 tolerance makes 80 % too easy (a model always answering 5 is within ±3 of any score from 2 to 8).
- **Labels rebalanced towards the extremes.** The first 30 labels were mostly 4-8: a constant "always 5" answer scored 25/30 (83 %) and passed the criterion. 5 mid articles were replaced by 15 very low (crypto, game news, politics, general-audience content, from feeds outside `feeds.yaml`) or very high ones (two or more core interests). With the 40 labels, the best constant answer ("always 6") scores 26/40 (65 %), below the 80 % target.
- **Benchmark candidates:** free tiers only, plus Claude Haiku 5.5 (decided with the project owner).
- **Free tiers re-checked after run 4 (2026-10-29)**, against the constraints in [llm-layer.md](llm-layer.md). Kept: **Gemini** (Flash-Lite free tier reported at about 15 requests/min and 500-1,000 requests/day, far above 50 calls/day; Google no longer publishes the numbers, the AI Studio console shows them). Possible but not chosen: Groq (8,000 tokens/min, would need about 8 s between calls; the project owner chose not to use it) and Cloudflare Workers AI (10,000 neurons/day, about 650 per run with Gemma 4; heavier setup with an account id). Rejected: Cerebras (free tier replaced by a 30-day trial in July 2026), OpenRouter free models (50 requests/day), Cohere (about 1,000 calls/month, a month needs 1,500), GitHub Models (reported retired in July 2026), NVIDIA NIM (prototyping only).
- **Claude Haiku 5.5 not benchmarked** (project owner's decision after run 5): Gemini reached 90 % for free; the 1 €/month budget is kept for later if the free tier disappears.
- **One adapter for the OpenAI-style chat completions APIs** (approved by the project owner): Mistral and Gemini accept the same request and answer with the same body, so they share `ChatCompletionsProvider`; each provider is a small description (URL, pacing, provider-only fields). Anthropic keeps its own adapter. The spec's "adding a provider means adding one adapter" still holds: a new compatible provider is one new description and one registry line.
- **Provider JSON mode, prompt unchanged** (after run 1, approved by the project owner): each adapter enables its provider's JSON mode as a request parameter when there is one; the prompt stays shared. `json_object` rather than Mistral's `json_schema`: the problem is syntax, and a schema in the adapter would duplicate `LLMScore`. Updates the phase 4 decision in [llm-layer.md](llm-layer.md).
- **Summary language: wait for the chosen model** (project owner's choice). The local phase 6 digest showed 9 of 10 English articles summarized in French by `ministral-14b-2512`, against the spec ("in the article's language"). The score is not affected, so the benchmark runs with the prompt unchanged; the language is checked on the chosen model in step 9, and the prompt is strengthened only if that model drifts too.

## Done when

- `uv run auto-rss-sorting eval` prints the three metrics for the configured provider.
- The benchmark results are recorded above, the production provider is chosen and set in `config.yaml`.
- We know whether the success criterion (80 % within ±3) is met.
- `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` pass.
- `security-auditor` has run (new adapters, config) and `spec-reviewer` has reviewed the branch before merging into `dev`.
