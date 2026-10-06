# T002 — UAT and locality reference tables, boundaries, name normalisation

Status: ready
Depends on: T001
Branch: task/T002-uat-reference

## Goal
Authoritative national tables of all administrative units (UATs) and their
component localities, keyed by SIRUTA code, with web-ready boundary polygons
and a tested name-normalisation helper that every later task will use.

## Context
Every other dataset joins to `siruta`. Projects in documents often name a
village rather than the UAT, so the locality → UAT mapping is needed for
matching (docs/ARCHITECTURE.md, entities `uat` and `locality`).

## Inputs
- `siruta`: the official SIRUTA nomenclature from INS. Find the current
  official file and record its exact URL and version or date.
- `lau_boundaries`: Eurostat GISCO LAU boundaries for Romania. Use the most
  recent year available. Check and document whether the LAU code equals the
  SIRUTA code of the UAT. If it does not, document the mapping and stop for
  review if more than 1% of units cannot be matched by code.

If either source is unreachable or the licence is unclear, stop and report.
Do not substitute an unofficial source without asking.

## Deliverables
1. `mt ingest siruta` and `mt ingest lau-boundaries`: download raw files per
   the scraping rules (raw folder plus manifest).
2. `mt normalise uat`: builds the tables below.
3. `data/processed/uat.parquet`, one row per UAT:
   `siruta` (int), `name` (str, diacritics normalised to comma-below),
   `name_key` (str, from `normalise_name()`), `uat_type` (enum: `comuna`,
   `oras`, `municipiu`, `municipiul_bucuresti`, `sector`), `county_code` (str,
   two-letter vehicle-plate code; `B` for Bucharest), `county_name` (str),
   `county_siruta` (int), plus provenance columns.
4. `data/processed/locality.parquet`, one row per component locality:
   `siruta` (int), `name`, `name_key`, `parent_uat_siruta` (int),
   `locality_type` (as given by the source, documented), `is_uat_seat`
   (bool, where the source provides it), plus provenance.
5. `data/processed/geo/uat_boundaries.parquet` (GeoParquet or WKB geometry,
   full resolution) and `data/export/geo/uat_boundaries.geojson` simplified
   for the web, keyed by `siruta`. Report the simplification tolerance and
   file size; target under 8 MB.
6. `mayortracker/util/names.py` with `normalise_name(text) -> NameNormalised`
   returning the display form (cedilla ş/ţ to comma-below ș/ț, Unicode NFC,
   trimmed whitespace) and a matching key (lowercase, ASCII-folded, punctuation
   removed, administrative prefixes such as "comuna", "oraș", "municipiul"
   removed). Thorough unit tests, including uppercase and mixed-diacritics
   cases.
7. Update the `siruta` and `lau_boundaries` rows in docs/DATA_SOURCES.md
   (status, exact URL, licence note).

## Allowed new dependencies
`geopandas`, `shapely`, `pyogrio` (add with `uv add`). Nothing else without asking.

## Requirements
1. SIRUTA codes stored as integers; check digits preserved as given.
2. Document in the handoff which SIRUTA fields identify the level (county,
   UAT, locality) and the urban/rural type, quoting the source documentation.
3. Every UAT appears exactly once; every locality has exactly one parent UAT.
4. Every UAT has exactly one boundary polygon, or is listed as unmatched.
5. Test fixtures are synthetic (TEST names, codes of 900000 or above after
   checking that range is unused).

## Acceptance criteria
- [ ] `uat.parquet` and `locality.parquet` built from raw files by
      `mt normalise uat`, reproducibly.
- [ ] Counts of UATs by `uat_type` and by county reported.
- [ ] Boundary match rate reported; unmatched units listed.
- [ ] `normalise_name()` tests pass, including ş→ș and ţ→ț.
- [ ] Simplified GeoJSON exists, under 8 MB, opens in a GeoJSON viewer
      (state which one you checked with).
- [ ] DATA_SOURCES.md rows updated.

## Out of scope
- Population data (a later task).
- Any historical boundary changes beyond noting them.

## Checks to report in the handoff
- Total UATs, and counts by type (the reviewer will compare with the roughly
  3,180 mayors Romania elects; explain any difference, for example Bucharest
  and its sectors).
- Total localities; number of UATs with zero component localities.
- Duplicate `name_key` values within the same county (list them: these will
  matter for matching).
- Boundary match rate and unmatched list.
- Source versions and dates.

## Notes and known pitfalls
- SIRUTA contains several levels (counties, UATs, localities). Filter by the
  documented level field, not by name patterns.
- Same-name communes exist in different counties; never match on name alone.
- Some data uses cedilla diacritics (ş ţ); normalise everywhere.
