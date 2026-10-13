# T005 — Kohesio: EU cohesion projects in Romania, matched to UATs

Status: done
Depends on: T002
Branch: task/T005-kohesio

## Goal
A clean table of all EU cohesion-policy projects in Romania from Kohesio, with their beneficiaries, and a documented match of beneficiaries that are local public authorities (communes, towns, municipalities, Bucharest and its sectors) to SIRUTA codes.

## Context
Layer "verified" in docs/SPEC.md: EU-funded projects and funds secured per UAT. Kohesio covers ERDF, Cohesion Fund and ESF (2014–2020, with 2021–2027 being added); it does not cover rural development (AFIR) or the Recovery and Resilience Plan (PNRR). Project locations are sometimes the beneficiary's address rather than the investment site.

## Inputs
- `kohesio` (docs/DATA_SOURCES.md): the official Kohesio bulk download of projects and beneficiaries. Use a country-level (Romania) download if one exists; otherwise the full download, filtered to Romania. Record exact URLs, dataset version or date, and licence.
- data/processed/uat.parquet and locality.parquet (T002), and `normalise_name()`.

## Step 0 (before writing parsing or matching code)
Find the official download through Kohesio's own documentation or data page, download it through the PoliteClient into data/raw/kohesio/<date>/, then report: files, formats, size, row counts for Romania, all column names, and which columns hold beneficiary name, beneficiary type or identifier, location (NUTS, LAU, coordinates), programme, fund, budget, EU co-financing, and start and end dates. Stop and wait for review.

## Deliverables (after review)
1. `data/processed/kohesio_projects.parquet`: one row per project (id, title, programme, fund, period, total budget, EU co-financing, start and end dates, location fields, provenance).
2. `data/processed/kohesio_beneficiaries.parquet`: one row per project–beneficiary pair.
3. `data/processed/beneficiary_uat_matches.parquet`: one row per beneficiary judged to be a local public authority, with `siruta` (or null), `match_method` (e.g. name_county_exact, name_county_normalised, location_point_in_polygon), `match_confidence`, and the evidence used.
4. `data/interim/kohesio/match_review.csv`: ambiguous or unmatched local-authority beneficiaries for manual review.
5. handoff/T005.md.

## Requirements
1. Rule-based matching only in this task (no LLM). Match a local-authority beneficiary to a UAT using its name plus county; never on name alone, since same-name communes exist in different counties.
2. Project location may support a match as secondary evidence, but never decides one alone.
3. Ambiguous cases go to the review file, not to a guess.
4. Keep county councils and other public bodies identified as such, but out of the UAT match.
5. Amounts stay in their source currency and units, as given.

## Acceptance criteria
- [ ] Step 0 report reviewed before parsing code is written.
- [ ] Projects and beneficiaries tables built reproducibly from raw files.
- [ ] Counts reported: Romanian projects; share with at least one local-authority beneficiary; matched / ambiguous / unmatched local authorities, by match method.
- [ ] Totals reported by fund and programme period; top 20 UATs by EU co-financing.
- [ ] `uv run ruff check .` and `uv run pytest` pass.

## Out of scope
LLM matching or classification; AFIR and PNRR projects; linking to procurement contracts; satellite verification.

## Limits
At most 30 requests per host in total, including exploration. Official Kohesio download and documentation only; no scraping of individual project pages.
