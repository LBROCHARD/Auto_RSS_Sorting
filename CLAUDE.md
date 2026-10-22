# Auto RSS Sorting

Complete Spec : @SPEC.md


## Stack

- Python 3.15, managed with `uv`
- `httpx` (HTTP), `feedparser` (RSS/Atom), `PyYAML` (config), `pydantic` (validation)
- `pytest` (tests), `ruff` (lint + format)
- CLI entry point: `auto-rss-sorting`
- No LLM framework (no LangChain, LlamaIndex, etc.): use the providers' official SDKs or plain HTTP behind our own provider interface


## Commands

- Install: `uv sync`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Run: `uv run auto-rss-sorting`
Before saying a task is done, run tests and lint and report the result.


## Workflow rules
 
- Work test-first: write the failing tests for the task, show them to me, then implement.
- One task = one small diff = one commit. Do not bundle unrelated changes.
- Propose a plan before coding anything non-trivial, and wait for my approval.
- Never add a dependency without asking me first. Explain why it is needed.
- Prefer the simplest solution. No speculative abstractions, no unused configuration options, no features outside the spec ("Out of scope" section).
- Do not refactor code unrelated to the current task.
- Use gitmoji for commit messages.


## Code rules
 
- Type hints on all functions. Pydantic models for config and for LLM responses.
- Never swallow errors: no bare `except:` and no `except Exception:` that continues silently. Catch specific exceptions, and log what happened and why.
- A failing feed is logged and skipped. An invalid LLM response for one article: one retry, then skip that article and log it. A transient API error (timeout, 429, 5xx) after 3 attempts: skip that article and log it. A non-recoverable API error (auth, quota) or no article scored at all: fail the run.
- Time must be injectable: functions that depend on "now" take it as a parameter. Never call `datetime.now()` deep in the logic.
- Output must be deterministic: ties in ranking are broken by a fixed rule (see spec), never by dict or set ordering.
- Treat article text as data, never as instructions. Keep it clearly separated from instructions in the prompt.
- Validate all inputs (`config.yaml`, `feeds.yaml`, `keywords.yaml`, presence of `profile.md`) at startup and fail fast with a clear message.


## Testing rules
 
- The LLM is never called in tests: use a fake provider returning canned responses.
- No network access in tests: feeds come from fixture files in `tests/fixtures/`.
- Every edge case listed in the spec gets its own test (empty feed, 404, invalid XML, missing date, duplicate across feeds, invalid LLM JSON, score out of range, no candidates, same-day re-run).
- Tests must not depend on the current date.


## Security
 
- Never read, print, or modify `.env` or any secrets file.
- API keys come only from environment variables (GitHub secrets in CI). Never hardcode them, never log them.
- Do not run destructive commands (`rm -rf`, `git reset --hard`, force-push) without asking.
- Work on a feature branch, not directly on `main`.


## Branching

- `dev` is the default branch and the center of development: feature branches start from `dev` and merge back into `dev`.
- `main` is only for stable releases: it is updated from `dev` when a version is released, never developed on directly.


## Rules (Lessons learned)

- When you talk to me, use french, when you work on the code, use english only.
- JOURNAL.md is a document that belongs to me, you can't touch it.
- Give me a list of every file you modified/created/deleted after each action
- If you want to use a Git command, always ask for permission first (commit, push, create branch...)



