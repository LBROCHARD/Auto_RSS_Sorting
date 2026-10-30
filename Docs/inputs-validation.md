# Phase 1: Inputs and validation

- **Status:** done, merged into `dev` (PR #2)
- **Branch:** `feature/inputs-validation` (from `dev`)
- **Global plan:** [PLAN.md](PLAN.md)

## Goal

Load and validate every input at startup: `config.yaml`, `feeds.yaml`, `keywords.yaml`, and the presence of `profile.md`. Any problem stops the run with a clear message naming the file and the field.

Out of this phase: wiring into the CLI (phase 6), checking `provider` against real adapters (phase 4).

## Design

One module, `src/auto_rss_sorting/inputs.py`:

- `InputError(Exception)`: the only exception raised by this module. Its message names the file and the problem.
- Pydantic models, all with `extra="forbid"` so a typo (`top-n`) fails instead of being ignored:
  - `Config`: `top_n`, `max_age_days`, `llm_max_articles`, `max_description_chars` (int > 0), `provider`, `model` (non-empty str), `price_input_per_mtok`, `price_output_per_mtok` (finite float >= 0). All fields required, no defaults: the values live in `config.yaml` only.
  - `Feed`: `name` (non-empty str), `url` (http/https URL).
  - `FeedList`: `feeds` (non-empty list of `Feed`), feed names and URLs unique.
  - `Keywords`: `keywords` (non-empty mapping keyword -> int weight), keywords non-empty, unique case-insensitively (`Rust` and `rust` are the same keyword).
- `Inputs`: a frozen dataclass holding `config`, `feeds`, `keywords`, `profile` (text of `profile.md`). Not a Pydantic model: it only groups values that are already validated.
- `load_inputs(base_dir: Path) -> Inputs`: reads the four files from `base_dir`, raises `InputError` on:
  - missing file, or file that cannot be read (not UTF-8, directory, permissions),
  - YAML syntax error, or YAML root that is not a mapping,
  - Pydantic validation error, formatted as one line per error: `config.yaml: top_n: Input should be greater than 0`,
  - `profile.md` empty (whitespace only).

File formats (consistent with the existing `feeds.yaml`, which has a top-level `feeds:` key):

```yaml
# config.yaml
top_n: 10
max_age_days: 7
llm_max_articles: 50
max_description_chars: 2000
# Provisional values: the provider and model are chosen in phase 4.
provider: undecided
model: undecided
price_input_per_mtok: 0
price_output_per_mtok: 0
```

```yaml
# keywords.yaml
keywords:
  rust: 3
  webgpu: 3
  crypto: -5
```

Known limits, accepted for v1:

- PyYAML silently keeps the last value when a key is duplicated in the same file (no custom loader).
- Keywords are stripped before the duplicate check, so `"rust"` and `"rust "` collapse into one key and the last weight wins silently. Same kind of typo as the duplicate key above.

## Steps

Each step is test-first (failing tests shown to you, then implementation) and ends with one commit.

- [x] **1. Dependencies.** Ask approval, then `uv add pydantic pyyaml`.
- [x] **2. `config.yaml`.** Tests: valid config loads; missing file; YAML syntax error; root not a mapping; missing field; unknown field; zero/negative values; negative price; empty provider. Then `Config` + the loading/error-formatting helper. Create `config.yaml` at the repo root.
- [x] **3. `feeds.yaml`.** Tests: valid list loads; empty list; missing name; invalid URL (not http/https); duplicate name; duplicate URL. Then `Feed` + `FeedList`.
- [x] **4. `keywords.yaml`.** Tests: valid mapping loads (positive and negative weights); empty mapping; non-integer weight; empty keyword; case-insensitive duplicate. Then `Keywords`. Create `keywords.yaml` from `profile.md` (draft weights, for you to review).
- [x] **5. `profile.md` and `load_inputs`.** Tests: missing profile; empty profile; `load_inputs` returns all four inputs; the real files committed at the repo root are valid. Then `load_inputs` and `Inputs`.
- [x] **6. Docs.** Tick this plan, mark the phase done in [PLAN.md](PLAN.md).

## Tests

- File: `tests/test_inputs.py`.
- Each test writes its files into pytest's `tmp_path` (inline YAML strings): the input next to the assertion is easier to read than a separate fixture file.
- Error tests assert on the message (file name and field present), not only on the exception type.
- One test loads the real repo files, so a broken committed config fails CI.

## Decisions

- **`provider` / `model` / prices in `config.yaml`:** provisional values (`undecided`, prices `0`) until the provider is chosen in phase 4.
- **Review fixes:** after the `spec-reviewer` pass, unreadable files and infinite prices also raise `InputError` (tests added). The whitespace collapse of keywords is kept as a known limit.
- **PyYAML is built as pure Python:** it ships no wheel for Python 3.15, and building its C extension needs a compiler. `pyproject.toml` sets `PYYAML_FORCE_LIBYAML=0` for its build (`[tool.uv.extra-build-variables]`). Slower parsing does not matter for a few small files.

## Done when

- All the tests above pass, `uv run ruff check .` and `uv run ruff format --check .` are clean.
- `spec-reviewer` has reviewed the branch before merging into `dev`.
