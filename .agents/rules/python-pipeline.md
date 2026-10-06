---
trigger: glob
globs: "**/*.py"
description: "Conventions for Python pipeline and test code."
---
 
# Python conventions
 
- Python 3.12, managed with `uv`. Add dependencies with `uv add <pkg>` (dev tools with `uv add --dev`). Do not add a dependency the brief does not need.
- Package layout: `pipeline/src/mayortracker/<stage>/<source_or_topic>.py`. Stages: `ingest`, `normalise`, `extract`, `link`, `indicators`, `export`.
- CLI: one `typer` app named `mt`; each stage and source is a subcommand. Every command has `--help` text.
- Paths come from the config loader, never hard-coded absolute paths.
- Record schemas are pydantic models in `pipeline/src/mayortracker/schemas/`. Parquet writes must enforce column types explicitly.
- Join keys: `siruta` is an integer and the primary key for administrative units. Never join on names when a code exists.
- Name matching: use the shared `normalise_name()` helper (diacritics to comma-below, ASCII-folded key, whitespace and prefix rules). Do not write ad-hoc normalisation.
- Logging with the standard `logging` module; no bare `print` in library code.
- Tests in `tests/` mirroring the package layout. Use small synthetic fixtures that obey the fixture rules in AGENTS.md. Network calls in tests must be mocked.
- Never weaken, skip or delete a failing test to make the suite pass. Report it instead.
