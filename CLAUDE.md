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
- Handle API keys with care:
  - read a key from the environment only where it is needed (the provider adapter), and never store it in a config file, a fixture, a docstring or a committed file;
  - never put a key in a log, an exception message, a `repr` or a test assertion output: error messages name the environment variable, never its value;
  - tests use obviously fake values (e.g. `"fake-key"`) set with `monkeypatch`, never a real key;
  - never print, `echo` or dump environment variables in shell commands (`env`, `printenv`, `set`), and never pass a key on a command line;
  - before every commit, check the diff for anything that looks like a secret; if one was ever committed, stop and tell me (the key must be revoked, deleting it in a new commit is not enough).
- Run the `security-auditor` agent before every merge (and before a commit that touches LLM providers, config, CI or fixtures). Report its findings to me; do not merge while a Critical or High finding is open.
- Gitleaks runs in CI on every push and pull request; a failing scan blocks the merge.
- Do not run destructive commands (`rm -rf`, `git reset --hard`, force-push) without asking.
- Work on a feature branch, not directly on `main`.


## Branching

- `dev` is the default branch and the center of development: feature branches start from `dev` and merge back into `dev`.
- `main` is only for stable releases: it is updated from `dev` when a version is released, never developed on directly.
- Every phase is developed on its own branch `feature/<feature-name>`, created from an up-to-date `dev`. One branch per phase at least: a large phase can be split into several branches, but a branch never spans two phases.


## Planning and progress tracking

- `Docs/PLAN.md` is the global roadmap: phases, their status, and a link to each phase plan. Read it at the start of every task to know where the project stands.
- Each phase has its own plan file `Docs/<feature-name>.md`, named after the feature (same name as its branch `feature/<feature-name>`), with a status line and steps as checkboxes. It is written and approved before the phase starts.
- Keep the docs up to date as you go: tick each step in the phase plan when it is done (in the same commit as the work), and update the phase status and "Current status" in `PLAN.md` when a phase starts or is merged.
- If a decision during the work changes the plan, update the plan file and tell me.
- Work outside a phase (a fix, a simple command) does not need a plan file.


## Rules (Lessons learned)

- Use gitmoji for commit messages.
- When you talk to me, use french, when you work on the code, use english only.
- JOURNAL.md is a document that belongs to me, you can't touch it.
- always include my modifications of JOURNAL.md in your commits, it's a file that grows with the project, it should be regularly pushed alongside it.
- After each action, I want you to present the work you did in a comprehensive way : make an ordered list of what you did and why, and list every files modified, created or deleted and what changed in them. Finish by a list of actions you wish to take next or questions to continue. 
  - I like to have thoses sections separated with a title in your response, it makes it more lisible.
- If you want to use a Git command, always ask for permission first (commit, push, create branch...)
- If the work you have to do is more than a fix or a simple command, it must be planned first. You can write plans in the file Docs/ in plain .md files.
- Each phase of the project must have a plan, with tasks. Never start working on a phase if it's not planned out first.
- Do not write "Generated with Claude Code" in PR messages, or anywhere else, it's useless
- Write an adecquate quantity of tests regarding the scope of the project, depending on the use case, maybe we don't need to test everything, try to stay cost efficient in development time in that regard.
- Do not ask for commit authorization during the work, ask for it in your response to let me the time to go check the notification.


