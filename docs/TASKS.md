# Task backlog

Status: `draft` → `ready` → `in progress` → `in review` → `done`
(or `blocked`). Agents update only their own task's status.

## Phase 0 — Foundations (national reference data)

| ID | Task | Depends on | Status |
|---|---|---|---|
| T001 | Repository bootstrap: Python project, CLI skeleton, config, tests, CI | — | done |
| T001a | HTTP helper hardening | T001 | in review |
| T002 | UAT and locality reference tables, boundaries, name normalisation | T001 | ready |
| T003 | Mayoral election results 2020 and 2024 | T001, T002 | ready |
| T003b | By-elections and mid-term changes of mayor, 2020–2024 term (actual term start and end dates) | T003 | draft |
| T004 | Link the same person across elections (2020 ↔ 2024) | T003 | draft |

## Phase 1 — Funds and contracts

| ID | Task | Depends on | Status |
|---|---|---|---|
| T005 | Ingest Kohesio (Romania) and match beneficiaries to UATs | T002 | draft |
| T006 | Ingest EU-FAR absorption dataset and local budget execution | T002 | draft |
| T007 | Ingest OpenTender Romania; contracts by contracting authority → UAT | T002 | draft |

## Phase 2 — Documents (pilot county)

| ID | Task | Depends on | Status |
|---|---|---|---|
| T008 | Discover and download Art. 155 annual reports | T002 | draft |
| T009 | Extract claimed projects from annual reports (LLM) + gold set | T008 | draft |
| T010 | Discover planned-project sources (strategies, budget annexes) | T002 | draft |
| T011 | Project linking across layers + review queue | T005, T007, T009 | draft |

## Phase 3 — Indicators and website

| ID | Task | Depends on | Status |
|---|---|---|---|
| T012 | Indicator computation, method v1 (needs a rule for partial terms from T003b) | T011 | draft |
| T013 | Website skeleton: map + mayor page from export JSON | T003, D003, D006 | draft |
