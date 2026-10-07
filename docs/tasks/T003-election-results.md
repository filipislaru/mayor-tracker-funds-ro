# T003 — Mayoral election results, 2020 and 2024

Status: ready
Depends on: T001, T002
Branch: task/T003-election-results

## Goal
Clean national tables of every mayoral race in the 2020 and 2024 local
elections: all candidates with party and votes, the winner, and the winning
margin, linked to `siruta`, with one row per resulting mayor-term.

## Context
Mayor-terms are the unit of analysis (D001). Margins are needed later for
close-race designs. Local elections were held on 27 September 2020 and
9 June 2024; mayors are elected in a single round by plurality.

## Inputs
- `aep_local`: official results from the Permanent Electoral Authority (AEP)
  for both elections, for the mayor ballot ("primar"), including
  the general mayor of Bucharest and the sector mayors. Find the official
  machine-readable files; record exact URLs. If only a third-party
  republication is machine-readable, stop and ask before using it.
- Results are usually published per polling station. Aggregate them to the
  race level (one race per UAT electoral circumscription) with a script,
  keeping the polling-station table. Where AEP also publishes
  circumscription-level totals, reconcile the aggregated totals against them
  and report every difference.
- `data/processed/uat.parquet` from T002.

## Deliverables
1. `mt ingest aep-local --year 2020|2024` (raw files plus manifest).
2. `mt normalise elections --year ...`.
3. `data/processed/mayor_candidates.parquet`, one row per candidate per race:
   `year` (int), `siruta` (int), `candidate_id` (str, stable within the
   dataset: year–siruta–ballot order), `candidate_name` (normalised display
   form), `name_key`, `party_raw` (str, exactly as in source),
   `party_normalised` (str or null), `is_independent` (bool),
   `is_alliance` (bool), `votes` (int), `vote_share` (float),
   `rank` (int), `is_winner` (bool), plus provenance.
4. `data/processed/mayor_races.parquet`, one row per race: `year`, `siruta`,
   `registered_voters`, `votes_cast`, `valid_votes`, `n_candidates`,
   `winner_candidate_id`, `winner_vote_share`, `runner_up_vote_share`,
   `margin_pp` (winner minus runner-up, in percentage points),
   `is_repeated_or_annulled` (bool, where the source records it), plus
   provenance.
5. `data/processed/mayor_terms.parquet`, one row per elected mayor:
   `term_id` (str, `<year>-<siruta>`), `siruta`, `election_year`,
   `term_start` (official validation date if available, else null),
   `planned_term_end` (null unless an official source states it),
   `candidate_id`, `mayor_name`, `party_normalised`, `margin_pp`.
6. `config/party_aliases.yaml`: mapping from `party_raw` to
   `party_normalised`, covering only names you can map unambiguously from the
   source itself (abbreviation and full name both appear). Everything else
   goes under an `unmapped:` list for review. Do not guess.
7. `data/processed/mayor_results_polling_station.parquet`: one row per
   candidate per polling station, with polling station identifier, the race's
   `siruta`, votes and provenance.

## Requirements
1. Every race joins to exactly one `uat.siruta`. Report and stop for review
   if more than 1% of races do not match.
2. Exactly one winner per race. Ties or missing votes are flagged, not
   resolved by assumption.
3. Sum of candidate votes compared with `valid_votes` for every race;
   discrepancies listed.
4. Partial and by-elections between the main elections are out of scope, but
   if the source mixes them in, flag and exclude them, and count them.

## Acceptance criteria
- [ ] Three parquet files built reproducibly for both years.
- [ ] Match rate to `uat.parquet` reported per year; unmatched listed.
- [ ] One-winner check passes, or failures listed.
- [ ] Vote-sum discrepancy table reported.
- [ ] `party_aliases.yaml` with a non-empty `unmapped` list where needed.
- [ ] DATA_SOURCES.md `aep_local` row updated.

## Out of scope
- Linking the same person across 2020 and 2024 (T004).
- Elections before 2020 (later task, same code path).
- County council elections.
- By-elections, resignations, deaths and removals: T003b.

## Checks to report in the handoff
- Number of races per year; compare with the number of UATs from T002.
- Distribution of `margin_pp`: count of races with margin under 1, 2 and 5
  points, per year.
- Share of independents and the 10 most frequent `party_normalised` values
  per year.
- Number of races with vote-sum discrepancies and the largest discrepancy.

## Notes and known pitfalls
- Candidate names may appear as SURNAME Firstname, with or without
  diacritics. Use `normalise_name()` from T002.
- Alliances appear under several spellings; keep `party_raw` untouched.
- Bucharest has a general mayor plus six sector mayors; check how the source
  encodes them and how they map to SIRUTA.
