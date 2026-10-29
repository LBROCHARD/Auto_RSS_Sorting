# Phase 8: Scheduling and v1 release

- **Status:** approved, not started
- **Branch:** `feature/scheduling` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Run the pipeline every day on GitHub Actions and commit the digest and the state to `main` (spec, "Execution"), write the README (with example output and the provider benchmark), and release v1 by merging `dev` into `main`.

*Done when:* a **scheduled** run (not only a manual one) has produced and committed a digest on `main`.

Out of this phase: any change to the pipeline itself. No new dependency, no Python code expected (if a step turns out to need some, it is test-first as usual).

## Design

### Where the workflow lives and which code it runs

GitHub only triggers `schedule` (and lists `workflow_dispatch`) for workflow files on the **default branch**, which is `dev` here. But the spec wants the digest and the state committed to `main`, and `main` is the stable release.

So the workflow file lives on `dev` (and therefore on `main` after the release), and its job explicitly checks out `main` (`actions/checkout` with `ref: main`): the daily run executes the released code, reads the state committed on `main`, and pushes back to `main`. `dev` never receives the live `digests/` and `state/`, so merging `dev` into `main` at the next release does not conflict with the bot's commits.

Consequence: the workflow cannot produce anything useful before v1 is on `main`. The release (step 5) comes before the first real run (step 6).

### `.github/workflows/daily.yml`

- **Triggers:** `schedule` with one daily cron in UTC, `0 5 * * *` (05:00 UTC, the digest is ready in the morning in France; GitHub may start scheduled runs a few minutes late, which is harmless since the digest date is the UTC date of the run), and `workflow_dispatch` with one boolean input `force` (default `false`) that adds `--force`.
- **Permissions:** `contents: write` (needed to push), nothing else.
- **Concurrency:** one group for the workflow, `cancel-in-progress: false`, so a manual run and the cron never write the state at the same time.
- **Steps:**
  1. `actions/checkout@v7` with `ref: main`.
  2. `astral-sh/setup-uv@v10.3.2` (same versions as `ci.yml`), then `uv sync --locked --no-dev` (the run needs no test tools; Python 3.15 comes from `.python-version`).
  3. `uv run auto-rss-sorting` (plus `--force` when the input is set), with `GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}` in the `env` of **this step only**. A failed run (exit 1: invalid input, fatal provider error, nothing scored) fails the job and nothing is committed, as the spec requires.
  4. Commit and push: `git add digests state`; if nothing is staged (same-day re-run without `--force` exits without changes), stop there with a log line; otherwise commit as `github-actions[bot]` with a gitmoji message (`:newspaper: Digest YYYY-MM-DD`, date taken from the UTC date) and `git push origin main`. `main` has no branch protection (checked with the project owner), so the bot can push.
- **No other workflow is triggered by the bot's push:** pushes made with `GITHUB_TOKEN` do not start workflows, so `ci.yml` and Gitleaks do not run on daily digest commits (they only contain generated Markdown and JSON).

### Example output: `examples/`

The project owner wants a few real digests and a state file committed as examples, linked from the README. They go in a separate folder, **`examples/digests/`** and **`examples/state/published.json`**, not in `digests/` and `state/`:

- the live `state/published.json` is read by the first scheduled run: if it held the entries of the local test runs, the first real digest would exclude those articles;
- `dev` keeps no live `digests/` or `state/` (see above), so releases never conflict with the bot's commits;
- an example folder makes it clear these files are a frozen sample, not the project's real history.

Content: the local digests of 2026-10-28 and 2026-10-29 (the second one is the run 6 digest, produced with the final prompt) and the matching `published.json`, copied as is. The security-auditor checks them like any other digest (public article data only). The local `digests/` and `state/` are then left untracked (or deleted by the project owner); they are not added to `.gitignore`, because `main` must track these folders.

### README

Replace the "work in progress" notice, and add:

- **Setup on a fork:** the `GEMINI_API_KEY` repository secret, enabling Actions, the branch layout (`dev` for development and the workflow file, `main` for releases and the daily commits).
- **Running it:** manual trigger from the Actions tab (with or without `force`), local run (`uv sync`, the environment variable, `uv run auto-rss-sorting`).
- **Example output:** links to `examples/digests/` and `examples/state/published.json`, with one line on what each file is; the live digests are in `digests/` on `main`.
- **Evaluation and provider benchmark:** why it matters (the LLM score is the whole product, so the spec defines a measurable success criterion: within ±3 points of hand scores for 80 % of 40 labelled articles; `eval` makes providers comparable by changing only `config.yaml`, and caught real problems: malformed JSON, an unusable free tier, summary language drift), a short version of the benchmark table from [eval.md](eval.md) (provider / model, accuracy, latency, free tier notes), the choice of Gemini and why (90 %, fastest, free, enough daily quota), how to run `eval`, and a link to [eval.md](eval.md) for the details.

Also fill the `description` field in `pyproject.toml` and set the version to `1.0.0`.

## Steps

One task = one commit on `feature/scheduling`.

- [ ] **0. Plan.** This file, plus the pending PLAN.md / `eval.md` updates marking phase 7 merged. One `:memo:` commit.
- [ ] **1. Workflow.** `.github/workflows/daily.yml` as designed above. Checked with a careful read and `security-auditor` (it touches CI and secrets); it cannot be run before step 5. One `:construction_worker:` commit.
- [ ] **2. Examples.** Copy the two local digests and `published.json` into `examples/`, `security-auditor` on them. One `:card_file_box:` commit.
- [ ] **3. README and version.** README sections above, `pyproject.toml` description and version `1.0.0` (`uv.lock` updated by `uv lock` if the version change requires it). One `:memo:` commit.
- [ ] **4. Merge into `dev`.** Tests, lint, format pass; `spec-reviewer` and `security-auditor` on the branch diff; PR `feature/scheduling` → `dev`.
- [ ] **5. Release v1.** PR `dev` → `main`, then a `v1.0.0` tag on `main`. Before the first run, the project owner (never me) adds the `GEMINI_API_KEY` repository secret.
- [ ] **6. First manual run.** The project owner starts the workflow from the Actions tab (`workflow_dispatch`, `force` off). We check the log (no key printed, failing feeds and skip counts as expected) and the commit on `main` (digest + state only). A second manual run the same day must end with "nothing to commit".
- [ ] **7. First scheduled run.** Wait for the next cron run, check its commit. Then tick this plan and mark phase 8 and v1 done in [PLAN.md](PLAN.md) (small `:memo:` commit on `dev`).

## Risks

- **Scheduled workflows are disabled by GitHub after 60 days without activity on a public repository.** Whether the bot's own daily commits count as activity is to be checked in the GitHub docs during step 1; if they do not, the README says how to re-enable the workflow.
- **Push rejected** if `main` moved during the run (e.g. a release merged at that moment): the job fails, nothing is lost, the next run (or a manual one) catches up. The concurrency group already prevents two runs racing each other; no automatic rebase, to keep the workflow simple.
- **Gemini free tier:** 500 requests/day, a daily run uses at most 150 (see [eval.md](eval.md)); a manual `--force` run on the same day adds up to 150 more, still within the limit.

## Decisions

- **Cron at 05:00 UTC, `v1.0.0` tag, no branch protection on `main`:** confirmed by the project owner.
- **Examples in `examples/`, not in `digests/` and `state/`** (see Design): the project owner asked for committed examples; a separate folder keeps them out of the live state.
- **Benchmark in the README** (project owner's request): a short table and its purpose; the full runs stay in [eval.md](eval.md).

## Tests

No new Python code, so no new pytest test. The workflow is verified by steps 6 and 7 (real runs), which is the phase's "done when" criterion. The existing suite, lint and format must stay green.
