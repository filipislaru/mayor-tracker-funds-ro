# AGENTS.md — Romania Mayor Tracker

This file is always loaded. It holds the non-negotiable rules for any coding
agent working in this repository. Read it in full before acting.

## What this project is

A public, reproducible database and website that records, for each Romanian
mayor and term of office:

- what was planned or promised,
- what the mayor reported as achieved,
- what independent records verify (procurement contracts, EU-funded and
  national-programme projects),
- funds secured, and
- procurement integrity risk indicators.

It will later support an academic paper, so every number must be
reproducible from raw sources by running code.

Spec: @docs/SPEC.md · Architecture: @docs/ARCHITECTURE.md ·
Sources: @docs/DATA_SOURCES.md · Decisions: @docs/DECISIONS.md

## How work is organised

- Work arrives as task briefs in `docs/tasks/Txxx-*.md`. Do exactly one task
  per conversation.
- Follow the `task-execution` skill. Finish with the `handoff-report` skill.
- The brief's acceptance criteria define "done". If a criterion cannot be met,
  stop and report it. Do not redefine the criterion.
- Do not edit `docs/SPEC.md`, `docs/ARCHITECTURE.md` or `docs/DECISIONS.md`
  unless the brief explicitly says so. You may update your task's status line
  in `docs/TASKS.md`, and the status column of rows in `docs/DATA_SOURCES.md`
  for sources the brief tells you to use.
- Stay inside the task's scope. No unrelated refactors, renames or upgrades.
- If something important is ambiguous, ask the user before proceeding rather
  than choosing silently.

## Data integrity (the most important section)

1. **Never invent data.** Never fabricate URLs, SIRUTA codes, names of people
   or places, party names, amounts, dates or document contents. If you cannot
   find or access a source, stop and report it as a blocker in the handoff.
2. **Never "estimate", "approximate" or "fill in" real-world values.** Missing
   is missing: store null and count it.
3. **Test fixtures must be visibly synthetic.** Use names prefixed `TEST`
   (e.g. `TEST Comuna Exemplu`) and SIRUTA codes of 900000 or above, after
   checking that range is absent from the real reference table. Fictional data
   never leaves `tests/`. Real data never goes into `tests/`.
4. **Provenance on every record.** Every row carries `source_id` (a key from
   `docs/DATA_SOURCES.md`), `source_url`, `retrieved_at` (UTC, ISO 8601) and
   the sha256 of the raw file it came from. Values extracted from documents
   also carry `doc_id`, page (where applicable), `extraction_method`, model
   name and `prompt_version`.
5. **Raw downloads are immutable.** Save them under
   `data/raw/<source_id>/<YYYY-MM-DD>/` with a `manifest.json` (URL, timestamp,
   sha256, size, HTTP status). Never edit raw files. Every transformation is a
   script in the repo.
6. **No manual edits to processed data.** Corrections go through a versioned
   corrections file (`config/corrections/*.yaml`) with a reason for each entry.
7. **Report what you observe.** Row counts, null rates, duplicates, unmatched
   records. Never hide or round away a problem.
8. **Never disable TLS certificate verification, including during exploration: no curl -k/--insecure, no verify=False, no ssl.CERT_NONE. If a certificate fails, stop and report.**

## Scraping and downloading

- Prefer official bulk downloads and APIs over scraping.
- Respect robots.txt. At most one request per second per host. Send a
  User-Agent containing the project name and the contact email from `.env`.
  Cache responses and retry with exponential backoff.
- Never bypass logins, paywalls, CAPTCHAs or rate limits. Never use anyone's
  credentials.
- Do not collect social-media content or reader comments.
- Full rules: `.agents/rules/scraping.md`.

## Personal data

Mayors and candidates are public figures; we process data about their public
role only. Do not collect, store or publish private-life information, family
members' names, home addresses, personal ID numbers or bank details, even if a
source document contains them. Asset and interest declarations are out of
scope until a dedicated task defines exactly which fields may be stored.

## Language and terminology

- Code, identifiers, comments and documentation: English.
- Data: preserve Romanian text exactly, but normalise diacritics to the
  comma-below forms (ș, ț, Ș, Ț), never the cedilla forms (ş, ţ, Ş, Ţ). Keep an
  ASCII-folded copy for matching.
- Never label a person or institution "corrupt" in code output, data fields or
  UI text. Use "risk indicator", "verified", "not verified", "not found in
  records".

## LLM extraction

Full rules: `.agents/rules/llm-extraction.md`. Summary: structured output
validated against a schema, deterministic settings, prompts versioned in the
repo, raw responses stored, and a verification status on every extracted
item. Nothing extracted by a model is shown publicly as fact without it.

## Code conventions

- Python 3.12, package at `pipeline/src/mayortracker`, managed with `uv`.
  Run everything with `uv run`.
- Lint and format with `ruff`. Test with `pytest`. Type hints everywhere;
  `pydantic` models for record schemas.
- Storage: Parquet under `data/processed/`, queried with DuckDB.
- Configuration in `config/*.yaml`. Secrets only in `.env` (never committed;
  `.env.example` lists the keys).
- Every pipeline step is a CLI subcommand: `uv run mt <step> [options]`.
  Steps are idempotent: running twice gives the same result.

## Before you finish

- `uv run ruff check .` and `uv run pytest` both pass.
- Outputs exist at the paths in the brief, with the stated schema.
- `handoff/Txxx.md` is written using the `handoff-report` skill.
- Work is committed on a branch named `task/Txxx-short-name`, with commit
  messages starting `Txxx:`. Do not push or merge unless the user asks.
