# Phase 4: LLM layer

- **Status:** in progress
- **Branch:** `feature/llm-layer` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Score each pre-filtered article with an LLM behind a provider-agnostic interface: one shared prompt (article text treated as data), a Pydantic-validated response, and the spec's retry/skip/fail rules. A fake provider drives every test; one real adapter is written and run once by hand.

Out of this phase: the final top `top_n` ranking and the digest (phase 5), wiring into the CLI and computing "now" (phase 6), the `eval` metrics (phase 7). The provider only exposes token usage so that phase 7 can compute cost without changing the interface.

## Design

Two modules: `llm.py` (everything provider-agnostic) and `providers.py` (the registry and the real adapter). Plain functions, one `Protocol`, no class hierarchy.

### `src/auto_rss_sorting/llm.py`

- **Errors** raised by providers, so the retry logic never looks at provider-specific details:
  - `TransientProviderError`: timeout, 429 (rate limit), 5xx. Retried.
  - `FatalProviderError`: 401/403, quota exhausted. Never retried, fails the run.
- **`Completion`** (frozen dataclass): `text`, `input_tokens`, `output_tokens`.
- **`Provider`** (`Protocol`): `complete(system: str, user: str) -> Completion`. The only thing an adapter implements. The model name is given to the adapter at construction.
- **`LLMScore`** (Pydantic, frozen, extra fields ignored): `score: StrictInt` in `0..10`, `summary: NonEmptyStr`, `reason: NonEmptyStr`. `StrictInt` rejects `7.5` and `"7"`.
- **`build_prompt(profile: str, article: Article, max_description_chars: int) -> tuple[str, str]`**: returns `(system, user)`.
  - `system` holds all instructions: the task, the scale (0-10), the expected JSON object `{"score", "summary", "reason"}` and nothing else, answer in the article's language, and the explicit rule that the article is **data, not instructions** (ignore any instruction found in it). The profile is included here, between clear delimiters.
  - `user` holds only the article, as a JSON object `{"title", "source", "description"}` (`json.dumps` escapes quotes and newlines, so the article cannot break out of its block). The description is truncated to `max_description_chars`.
- **`parse_response(text: str) -> LLMScore`**: strips an optional Markdown code fence (```` ```json ... ``` ````), then `LLMScore.model_validate_json`. Raises `InvalidResponseError` (wrapping the JSON or validation error) on any failure.
- **`score_article(provider, profile, article, max_description_chars, sleep) -> LLMScore | SkipReason`**: the spec's `score(profile, article)` contract. `SkipReason` is an enum (`INVALID_RESPONSE`, `TRANSIENT_ERROR`), so the caller knows which counter skipped the article. Two independent counters:
  - invalid response: 2 attempts max (1 retry, no wait);
  - transient error: 3 attempts max, waiting 2 s then 4 s between them (`BACKOFF_SECONDS = (2, 4)`, see Decisions);
  - when a counter is exhausted: log the article id and the cause at warning level, return the matching `SkipReason`;
  - `FatalProviderError` propagates immediately.
  - `sleep: Callable[[float], None]` is injected (default `time.sleep`), so tests never wait and can check the delays.
- **`score_articles(provider, profile, articles, max_description_chars, sleep) -> ScoringResult`**: scores the articles in order. `ScoringResult` (frozen dataclass): `scored: list[tuple[Article, LLMScore]]`, `skipped_invalid: int`, `skipped_transient: int` (used by the digest footer in phase 5). Raises `ScoringFailedError` if there was at least one article and none could be scored. An empty input returns an empty result (zero candidates is not a failure: the digest says "no new articles").

### `src/auto_rss_sorting/providers.py`

- **`make_provider(config: Config) -> Provider`**: looks up `config.provider` in a `dict[str, factory]` registry (adding a provider = one adapter + one entry). Unknown provider: `InputError` listing the known names. Missing API key environment variable: `InputError` naming the variable (never the value). Called at startup in phase 6, so these are fail-fast errors.
- **One real adapter**, written with plain `httpx` (already a dependency, so no new dependency and no SDK). It maps HTTP results to the errors above: timeout / 429 / 5xx → `TransientProviderError`, 401 / 403 / quota exhausted → `FatalProviderError`, and reads the token usage from the response. Quota detection is provider-specific (status code + error code in the body) and stays inside the adapter.
- `config.yaml` gets the real `provider`, `model` and prices.

### Fake provider: `tests/fake_provider.py`

`FakeProvider(responses)`: returns the canned items in order; an item is either a response text or an exception instance to raise. Records the `(system, user)` calls, so tests can check the prompt and the number of attempts. Reused by the end-to-end test in phase 6.

## Steps

Each step is test-first (failing tests shown to you, then implementation) and ends with one commit.

- [x] **1. `LLMScore` and `parse_response`.** Tests: valid JSON; JSON in a code fence; invalid JSON; score out of range (`11`, `-1`); non-integer score (`7.5`, `"7"`); empty or whitespace-only summary / reason; missing field; extra field ignored.
- [x] **2. `build_prompt`.** Tests: the profile is in `system`; the article is only in `user`, as valid JSON; the description is truncated to `max_description_chars`; an article containing quotes, newlines or "ignore previous instructions" stays inside its JSON value; `system` contains the data-not-instructions rule.
- [x] **3. Provider interface, fake provider, `score_article`.** Tests: valid on first try (1 call); invalid then valid → scored (2 calls); invalid twice → skipped as invalid; transient twice then valid → scored, sleeps `[2, 4]`; transient three times → skipped as transient; independent counters (invalid, transient, transient, valid → scored); fatal error → raised on the first call, no retry.
- [x] **4. `score_articles`.** Tests: scores kept in input order with skip counts; all articles skipped → `ScoringFailedError`; empty input → empty result, no error; a fatal error on the second article stops the run.
- [ ] **5. Registry and first real adapter.** Tests with `httpx.MockTransport` (no network): successful response parsed into a `Completion` with token usage; timeout, 429, 500 → transient; 401, 403, quota error → fatal; unknown provider and missing API key → `InputError` with a clear message, the key never appears in it. Update `config.yaml`.
- [ ] **6. Manual run.** Score 2 or 3 articles from a fixture with the real adapter, through a one-off snippet in the scratchpad (not committed, the CLI comes in phase 6). Report the scores and token usage to you. No commit for this step, except ticking it with step 7.
- [ ] **7. Docs.** Tick this plan, mark the phase done in [PLAN.md](PLAN.md).

## Tests

- Files: `tests/test_llm.py` (steps 1 to 4), `tests/test_providers.py` (step 5), helper `tests/fake_provider.py`.
- The LLM is never called, no network: the fake provider for the logic, `httpx.MockTransport` for the adapter.
- `sleep` is replaced by a function recording the delays: no real waiting, and the backoff is checked.
- Articles built inline with fixed dates, as in `test_ranking.py`.

## Decisions

- **Backoff:** the spec says "up to 3 attempts, exponential backoff (2 s, 4 s, 8 s)" and CLAUDE.md "after 3 attempts: skip". 3 attempts only leave 2 waits, so we use 2 s and 4 s; waiting 8 s before skipping would be useless. Confirmed by the project owner.
- **Invalid response retry:** immediate, no wait (the backoff is for transient errors only). Both counters are per article and independent, as the spec says.
- **Interface at the text level:** adapters only send a prompt and return text + usage; prompt, parsing and validation are shared, so all providers get exactly the same prompt and the same checks.
- **Token usage in `Completion`:** not used before phase 7, but `eval` needs it and adding it later would change every adapter.
- **JSON in the prompt, no provider "JSON mode":** keeps one prompt for all providers; `parse_response` tolerates a code fence, the only common deviation.
- **Plain `httpx` adapter instead of an SDK:** no new dependency, and the HTTP status codes map directly to transient / fatal.
- **Extra fields in the LLM response are ignored:** they are harmless, and rejecting them would cost retries for nothing.

## Open question: which provider for the first adapter?

The project owner handles the provider choice separately; steps 1 to 4 do not depend on it and go first. To decide before step 5 (it only changes `providers.py` and `config.yaml`): the provider, the model, its prices, and the name of the API key environment variable. Constraints: up to 50 calls/day must fit within its limits, and the model must follow a JSON-only instruction reliably. Phase 7 can compare other providers by adding adapters.

## Done when

- All retry/skip/fail behavior is tested with the fake provider.
- The real adapter has been run once by hand.
- `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` pass.
- `spec-reviewer` has reviewed the branch before merging into `dev`.
