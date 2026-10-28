# Phase 7: `eval` subcommand and provider benchmark

- **Status:** in progress
- **Branch:** `feature/eval` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Measure the spec's success criterion: on the 20 hand-scored articles of `eval/labels.csv`, the LLM score is within ±3 points of the owner's score for at least 80 % of them. An `auto-rss-sorting eval` subcommand runs the configured provider/model on this set and prints accuracy, cost per 100 articles and average latency. Then benchmark 3 or 4 provider/model pairs with it, pick the production provider (budget: at most 1 € per month) and record the results here.

Out of this phase: the GitHub Actions workflow and the README (phase 8). No score cache, no new dependency: `csv` from the stdlib, `pydantic`, `httpx` for new adapters.

## Design

One new module, `src/auto_rss_sorting/evaluation.py`, and a subcommand in `cli.py`. Plain functions, as in the previous phases.

### `eval/labels.csv` (provided by the project owner)

- Columns `url,title,description,score` (spec), UTF-8, standard CSV quoting (a description containing a comma is quoted).
- 20 rows, scored by hand **before** looking at any LLM output. To make the measure meaningful: a spread of scores (some low, some mid, some high), a mix of French and English articles, descriptions copied as the feeds give them.
- Committed: the articles are public and the scores say nothing personal beyond `profile.md`.

### `evaluation.py`

- **`Label`** (Pydantic, frozen, extra fields forbidden): `url: HttpUrl`, `title: NonEmptyStr`, `description: str` (may be empty, like a feed), `score: int` in `0..10`.
- **`load_labels(path: Path) -> list[Label]`**: fail fast with `InputError` and a message naming the file and the row: file missing, wrong header, invalid row (bad URL, score not an integer or out of range, empty title), no rows, duplicate URL (after normalization, with the existing `normalize_url`).
- **`label_to_article(label) -> Article`**: the label becomes an `Article` so the **exact production prompt** is used (`build_prompt` via `score_article`). `source` is the URL's host (the CSV has no source column), `published_at` is a fixed placeholder (the prompt does not use it).
- **`evaluate(provider, profile, labels, max_description_chars, config) -> EvalReport`**: scores each label with `score_article` (same retry rules as production: one retry on invalid response, 3 attempts on transient errors). A `MeteredProvider` wrapper around the provider adds up the token usage and latency of **every** call, retries included (they are real costs).
  - `EvalReport` (frozen dataclass): per-article results (human score, LLM score or skip reason), `within_tolerance`, `total`, `input_tokens`, `output_tokens`, `calls`, `total_latency_seconds`.
  - **Accuracy** = articles with `|llm - human| <= 3` / number of labels. A skipped article counts as a miss: the criterion is about the 20 articles, not only the ones that could be scored.
  - **Cost per 100 articles** = `(input_tokens × price_input_per_mtok + output_tokens × price_output_per_mtok) / 1,000,000 / number of labels × 100`.
  - **Average latency** = total latency / number of calls.
  - `FatalProviderError` propagates (eval fails). If no article could be scored: `ScoringFailedError`, as in a daily run.
- **Latency measurement:** the Mistral adapter waits up to 2 s before a call (free-tier pacing). Timing `complete()` from outside would count that wait as latency and penalize paced providers unfairly. So `Completion` gets a `latency_seconds: float` field, measured by the adapter around the HTTP request only, with its already injected clock. `FakeProvider` returns a fixed value.
- **`format_report(report, config) -> str`**: plain text printed on stdout (the command's result; logs stay on stderr):

  ```
  eval: mistral / ministral-14b-2512, 20 articles
  human  llm  diff  title
      8    7    -1  Rust 2.0 is out
      2    -      -  Some article (skipped: invalid LLM response)
  ...
  accuracy: 17/20 within ±3 points (85 %), target 80 %: met
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
- [ ] **2. Latency in `Completion`.** The Mistral adapter measures the HTTP request only, not the pacing wait (test with the injected clock: a paced call reports the request time, not the wait). `FakeProvider` updated.
- [ ] **3. `evaluate` and `EvalReport`.** Tests with `FakeProvider`: diff of exactly 3 counts as within, 4 does not (both directions); a skipped article counts as a miss; cost computed from the tokens of every call, retries included; average latency over all calls; prices at 0 → cost 0; fatal error propagates; nothing scored → `ScoringFailedError`; the prompt sent is the production prompt (title, host as source, description truncated).
- [ ] **4. `format_report` and the `eval` subcommand.** Tests: report text for a small fixed `EvalReport` (target met / not met, skipped row); `main(["eval"])` with a missing `eval/labels.csv` → exit 1 and a message naming the file; missing API key → exit 1; `main([])` still runs the daily pipeline path (existing tests stay green).
- [ ] **5. Labels.** You write `eval/labels.csv` (20 rows, see above). I validate it by running `load_labels` on it, without calling any LLM. Committed with step 6's results or on its own.
- [ ] **6. First eval: current provider.** You run `uv run auto-rss-sorting eval` with your `MISTRAL_API_KEY` (I never read `.env` nor pass a key on a command line). We record the three metrics here and check the language drift seen in phase 4 (English article answered in French) on the per-article results.
- [ ] **7. Benchmark, same adapter.** Other Mistral models need only a `config.yaml` change: `mistral-small-2603` and `ministral-8b-2512` (see the limits recorded in [llm-layer.md](llm-layer.md)). Run eval for each, record the results.
- [ ] **8. Benchmark, new adapter(s).** One adapter per new provider (plain `httpx`, same error mapping and security rules as the Mistral adapter, tests with `httpx.MockTransport`), one commit each, then one eval run. Decided with the project owner: free tiers only, plus Claude Haiku 5.5 (the only paid candidate, cheap). So one new adapter, for Anthropic (`ANTHROPIC_API_KEY`). Another free provider is added only if one meets the constraints listed in [llm-layer.md](llm-layer.md) (50 calls/day without 429s, reliable JSON in French and English); the ones rejected in phase 4 stay rejected unless their limits changed. Exact API details and prices are checked in the provider's official docs at the start of the step, not from memory.
- [ ] **9. Decision.** Fill the benchmark table, pick the production provider, set it in `config.yaml` (provider, model, prices). If no pair reaches 80 %, we discuss before changing anything (prompt wording, model, or the labels themselves).
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
| mistral / ministral-14b-2512 | | 0 | 0 | | 937,500 tok/min, 0.5 req/s | current |
| mistral / mistral-small-2603 | | | | | 20,000 tok/min | |
| mistral / ministral-8b-2512 | | | | | 625,000 tok/min, 3.13 req/s | |
| anthropic / Claude Haiku 5.5 | | | | | paid, no free tier | must fit 1 €/month |

## Decisions

- **Same prompt and retry rules as production.** Eval measures what the daily run will actually do; a separate eval prompt would measure something else.
- **Skipped article = miss.** The spec counts on the 20 articles; ignoring skips would reward an unreliable provider.
- **Retries count in cost and latency.** They are paid and waited for in production too.
- **Latency measured by the adapter** around the HTTP request, so a provider's free-tier pacing does not count as latency (see Design).
- **No currency in the code.** Prices in `config.yaml` are in the provider's billing currency; the benchmark table converts to euros by hand for the 1 € budget.
- **Eval exit code is 0 even below 80 %.** It is a measuring tool, not a gate; the report says whether the target is met.
- **`source` = URL host** for eval articles: the CSV has no source column (spec), and the prompt expects one.
- **No mean absolute error in the report.** Not in the spec; the per-article lines already show how far each score is. The labels must cover the whole 0-10 range, otherwise the ±3 tolerance makes 80 % too easy (a model always answering 5 is within ±3 of any score from 2 to 8).
- **Benchmark candidates:** free tiers only, plus Claude Haiku 5.5 (decided with the project owner).

## Done when

- `uv run auto-rss-sorting eval` prints the three metrics for the configured provider.
- The benchmark results are recorded above, the production provider is chosen and set in `config.yaml`.
- We know whether the success criterion (80 % within ±3) is met.
- `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` pass.
- `security-auditor` has run (new adapters, config) and `spec-reviewer` has reviewed the branch before merging into `dev`.
