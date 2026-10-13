# T006 — EU funds received: local budget execution

Status: ready
Depends on: T002, T005
Branch: task/T006-eu-received

## Goal
For every UAT and year, the EU funds actually received through its budget, from official local budget execution data.

## Context
Decision D012: this is the "received" stage, to compare with "contracted" (T005) and "completed" (T005b). The EU-FAR dataset is a possible later cross-check and is out of scope here.

## Inputs
- `budget_exec`: official local budget execution data per UAT and year, from the responsible ministry's own publications. Find the official source; download through the PoliteClient. If access needs a login or is blocked, stop and report.
- data/processed/uat_fiscal_codes.parquet and uat.parquet.

## Step 0 (before writing parsing code)
Report the structure of the source: files, years covered, formats, columns, and how UATs are identified. Identify which budget classification lines record EU funds received or spent, quoting the official classification documentation you accessed, with its URL. Stop and wait for review.

## Deliverables (after review)
1. `data/processed/uat_budget_eu_lines.parquet`: siruta, year, classification code, label, amount, unit, provenance.
2. `data/processed/uat_eu_received_year.parquet`: one row per UAT and year.
3. handoff/T006.md, including internal consistency checks (for example, EU revenue lines against EU-funded expenditure lines where both exist).

## Requirements
1. Classification codes come only from official documentation actually accessed, never from memory.
2. Amounts stay in their source currency and units, without conversion.
3. Match UATs by SIRUTA where present, otherwise by fiscal code from the T005 crosswalk; report unmatched rows, never drop them.

## Acceptance criteria
- [ ] Step 0 reviewed before parsing code is written.
- [ ] Coverage reported: UATs with data per year; unmatched rows listed.
- [ ] Totals per year and the internal consistency checks.
- [ ] `uv run ruff check .` and `uv run pytest` pass.

## Out of scope
EU-FAR; completion analysis; linking amounts to individual projects.

## Limits
At most 30 requests per host in total, including exploration. No automation of logins or CAPTCHAs.
