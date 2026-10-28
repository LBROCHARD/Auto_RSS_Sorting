# Phase 6: CLI and end-to-end pipeline

- **Status:** in progress
- **Branch:** `feature/cli-pipeline` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Wire the tested pieces of phases 1 to 5 into the `auto-rss-sorting` command: "now" computed once at the entry point, logging, `--force`, exit codes. An end-to-end test runs the whole pipeline with fixture feeds and the fake provider.

Out of this phase: the `eval` subcommand (phase 7), the GitHub Actions workflow and the README (phase 8). No new dependency: `argparse` and `logging` from the stdlib.

## Design

One new module, `src/auto_rss_sorting/cli.py`, with two functions: `run` holds the order of a run and takes every dependency as a parameter (testable without network or LLM), `main` builds the real dependencies and turns errors into exit codes.

### `run(inputs, provider, client, base_dir, now, force) -> None`

Parameters: `inputs: Inputs`, `provider: Provider`, `client: httpx.Client`, `base_dir: Path` (holds `digests/` and `state/`), `now: datetime` (UTC), `force: bool`. `today = now.date()`.

Order, as foreseen in [digest-state.md](digest-state.md):

1. `load_state(base_dir / "state/published.json")`: an invalid state fails the run before any work (`StateError`).
2. `already_published(digests_dir, today)` and not `force` → log "digest already exists, nothing to do" and return, nothing written, no feed fetched, no LLM call.
3. If `force`: `drop_digest_date(entries, today)`. Then `purge(entries, now, max_age_days)`.
4. `fetch_all(client, feeds)` → `collect_candidates(articles, now, max_age_days)` → `exclude_published` → `prefilter(candidates, compile_keywords(keywords), llm_max_articles)` → `score_articles(provider, profile, kept, max_description_chars)`.
5. `top_articles(scored, top_n)` → `RunReport` built from `FetchResult` and `ScoringResult` → `publish(...)`.
6. Log a summary line: digest path, number of articles, failed feeds, skip counts.

`FatalProviderError` and `ScoringFailedError` propagate from step 4, before anything is written: no digest, state unchanged (spec: the run fails, no digest is produced).

### `main(argv: list[str] | None = None) -> int`

- `argparse`: one optional flag `--force` ("regenerate today's digest"). Usage errors exit with code 2 (argparse default).
- Logging: `logging.basicConfig(level=INFO)` on stderr, format `time level logger: message`. The existing modules already log through `logging.getLogger(__name__)`.
- `now = datetime.now(UTC)`: the only call to "now" in the code.
- `base_dir = Path.cwd()`: the inputs, `digests/` and `state/` live at the repo root, where the Action runs.
- `inputs = load_inputs(base_dir)`, `provider = make_provider(inputs.config)` (fail fast: unknown provider, missing API key), `with make_http_client() as client: run(...)`.
- Exit codes: `0` digest published or same-day no-op; `1` for the expected failures (`InputError`, `StateError`, `FatalProviderError`, `ScoringFailedError`), logged as one clear `error:` line without traceback. Any other exception (bug, disk error) propagates with its traceback (exit code 1 from Python): never swallowed.
- The entry point in `pyproject.toml` becomes `auto_rss_sorting.cli:main`: the generated console script calls `sys.exit(main())`, so the returned int is the exit code. The "Hello" placeholder in `__init__.py` and its smoke test are removed.

## Steps

Each step is test-first (failing tests shown to you, then implementation) and ends with one commit.



- [x] **1.** `run`**, end to end.** Tests (in `tmp_path`, feeds served from `tests/fixtures/` through `httpx.MockTransport`, `FakeProvider`, fixed `now`):
  - happy path: the digest lists the expected articles in score order, a 404 feed is named in the footer, the state holds the published articles;
  - same-day re-run without `--force`: digest and state unchanged, provider never called;
  - same-day re-run with `--force`: digest regenerated, today's articles scored again, state holds them once;
  - next-day run: articles published the day before are excluded;
  - no candidate (all too old): digest with "No new articles today." and the footer, provider never called;
  - `FatalProviderError` during scoring: the error propagates, no digest, state unchanged.
- [ ] **2.** `main`**: arguments, logging, exit codes, entry point.** Tests (`monkeypatch.chdir(tmp_path)`, no network): invalid `config.yaml` → exit code 1 and a message naming the file; missing API key (`monkeypatch.delenv`) → exit code 1 and a message naming the variable; unknown option → exit code 2. Removes the smoke test.
- [ ] **3. Manual run.** You run `uv run auto-rss-sorting` locally with your real `MISTRAL_API_KEY` in your shell (I never read `.env` nor pass a key on a command line). We check the digest together. The produced `digests/` and `state/` files are not committed on the feature branch (the Action commits them to `main` in phase 8). No commit for this step.
- [ ] **4. Docs.** Tick this plan, mark the phase done in [PLAN.md](PLAN.md).

## Tests

- New file `tests/test_cli.py`; `tests/test_smoke.py` is removed (step 2).
- A small helper writes the four input files into `tmp_path` (`feeds.yaml` pointing to fake URLs that the `MockTransport` maps to fixture files). Reuses the existing fixtures (`rss_valid.xml`, `atom_valid.xml`) unless their dates make a scenario impossible, in which case one dedicated fixture is added.
- `FakeProvider` gets one canned response per expected call; its `calls` list proves when the LLM is not called.
- `now` is always explicit in `run` tests; `main` tests only cover paths that fail before `now` matters, so no test depends on the current date. The same-day re-run is tested on `run`, with a fixed `now`.
- Retry and skip rules, digest format and state cases are already tested in phases 4 and 5: not repeated here.

## Decisions

- **Same-day check after validation.** Inputs, provider (API key) and state are all validated before the same-day check, so a broken setup is always reported, even on a no-op day. The cost: a re-run needs the API key even when it does nothing, which is always the case in the Action.
- `run` **takes its dependencies,** `main` **builds them.** No other abstraction: no pipeline class, no config for paths.
- `base_dir` **is the current directory**, no `--dir` option (not in the spec).
- **Expected failures without traceback, unexpected ones with it**: the log stays readable for known cases, and nothing is hidden.

## Done when

- `uv run auto-rss-sorting` produces a real digest locally (step 3).
- The end-to-end scenarios above are tested, including the same-day re-run.
- `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` pass.
- `spec-reviewer` has reviewed the branch before merging into `dev`.
