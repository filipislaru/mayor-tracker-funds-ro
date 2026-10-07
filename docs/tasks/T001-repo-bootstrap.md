# T001 — Repository bootstrap

Status: ready
Depends on: —
Branch: task/T001-repo-bootstrap

## Goal
A working Python project with the `mt` CLI, configuration loading, data
folders, tests and continuous integration, ready for data tasks. No data is
downloaded in this task.

## Context
See AGENTS.md (code conventions) and docs/ARCHITECTURE.md (repository
layout). Decision D003 (stack) is proposed; this task covers only the Python
side.

## Inputs
None.

## Deliverables
1. `pyproject.toml` at the repo root (uv-managed), package `mayortracker` in
   `pipeline/src/mayortracker/`, console script `mt`.
2. Runtime dependencies: `typer`, `pydantic`, `pyyaml`, `httpx`, `duckdb`,
   `pyarrow`, `pandas`, `python-dotenv`. Dev dependencies: `pytest`, `ruff`.
3. Package skeleton: subpackages `ingest`, `normalise`, `extract`, `link`,
   `indicators`, `export`, `schemas`, `util`, each with `__init__.py`.
4. `config/settings.yaml` with: `project_name`, `data_dir` (default `data`),
   `pilot_county` (null), `http.min_seconds_between_requests` (1.0),
   `http.max_retries` (5). A config loader in `mayortracker/util/config.py`
   returning a pydantic settings object; environment variables from `.env`.
5. `mt` CLI (typer) with:
   - `mt --help`
   - `mt doctor`: prints Python version, uv-managed environment status, whether
     each data directory exists, and for each key in `.env.example` whether it
     is set in the environment (`set` / `missing`, never the value).
   - `mt init-data`: creates `data/raw`, `data/interim`, `data/processed`,
     `data/export`, `data/cache/http` if missing.
6. A shared HTTP helper `mayortracker/util/http.py` implementing the scraping
   rules (User-Agent from settings and `CONTACT_EMAIL`, per-host rate limit,
   retries with backoff honouring `Retry-After`, on-disk cache in `data/cache/http/`, raw saving with
   `manifest.json`). It is not used yet; it is tested with mocked responses.
7. Tests in `tests/`: CLI help and doctor run; config loads from a temporary
   YAML file; HTTP helper rate limiting, retry and manifest writing with a
   mocked transport (no real network).
8. GitHub Actions workflow `.github/workflows/ci.yml` running `uv sync`,
   `uv run ruff check .`, `uv run pytest` on push and pull request.
9. `README.md` updated with setup steps (install uv, `uv sync`, `uv run mt
   doctor`).

## Requirements
1. `uv run mt --help` lists `doctor` and `init-data`.
2. `uv run mt doctor` exits 0 and never prints secret values.
3. The HTTP helper refuses to run if `CONTACT_EMAIL` is missing.
4. No test performs real network access.
5. `ruff` configured in `pyproject.toml` (line length 100, rules E, F, I, B, UP).

## Acceptance criteria
- [ ] `uv sync` works on a fresh clone.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run pytest` passes, with tests covering items 5–7.
- [ ] `uv run mt doctor` output shown in the handoff.
- [ ] CI workflow file present and valid YAML.
- [ ] `data/` is entirely git-ignored; `mt init-data` creates its folders.

## Out of scope
- Downloading any data.
- Any website code.
- Choosing an LLM provider.

## Checks to report in the handoff
- Output of `uv run mt doctor`.
- `uv run pytest` summary line and number of tests.
- `uv tree` (top level only) or the dependency list with versions.

## Notes and known pitfalls
- Keep the HTTP helper small and well tested; every later ingest task depends
  on it.
- Use `src` layout so tests import the installed package, not files by path.
