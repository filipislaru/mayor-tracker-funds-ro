# Architecture

## Data flow

```
sources ──ingest──▶ data/raw/ (immutable, manifest.json per download)
        ──normalise──▶ data/interim/ (cleaned tables, crawl logs, LLM raw outputs)
        ──extract──▶ project mentions from documents (LLM, schema-validated)
        ──link──▶ mentions resolved into projects, matched to contracts and funds
        ──indicators──▶ data/processed/*.parquet (one row per mayor-term × indicator)
        ──export──▶ data/export/*.json (static files the website reads)
```

Each arrow is a CLI subcommand of `mt`, idempotent and logged.

## Core entities

| Entity | Key | Notes |
|---|---|---|
| `uat` | `siruta` | All communes, towns, municipalities, Bucharest and its sectors |
| `locality` | `siruta` | Villages and component localities, each with its parent UAT; needed to place projects that name a village |
| `election_race` | (`year`, `siruta`) | One mayoral race |
| `candidate_result` | (`year`, `siruta`, `candidate_id`) | Votes, party, winner flag |
| `mayor_term` | `term_id` | `siruta`, person, start and end dates, party at election, margin |
| `source_document` | `doc_id` | URL, `source_id`, `retrieved_at`, sha256, type |
| `project_mention` | `mention_id` | A project as it appears in one document, with layer (planned, claimed, verified), quote, extracted fields and verification status |
| `project` | `project_id` | A resolved real-world project in one UAT |
| `project_link` | (`mention_id`, `project_id`) | Match confidence, method, reviewer |
| `contract` | OCDS id | From procurement data |
| `eu_project` | source project id | From Kohesio and other EU sources |
| `programme_project` | source id | PNDL, Anghel Saligny |
| `indicator_value` | (`term_id`, `indicator`, `method_version`) | Final values with method version |

## Repository layout

```
AGENTS.md                 rules for coding agents (always on)
.agents/rules/            scoped rules (scraping, LLM, Python, website)
.agents/skills/           task-execution, handoff-report
docs/                     spec, architecture, sources, decisions, tasks, workflow
config/                   settings.yaml, party_aliases.yaml, corrections/
pipeline/src/mayortracker/
    ingest/ normalise/ extract/ link/ indicators/ export/ schemas/ util/
pipeline/prompts/         versioned LLM prompts
eval/                     hand-labelled gold sets per extraction/matching task
tests/                    pytest, synthetic fixtures only
data/                     git-ignored: raw/ interim/ processed/ export/
site/                     static website (built from data/export/)
handoff/                  one report per finished task
```

## Website (proposed, see D003)

Static site built from `data/export/`, deployed with GitHub Pages via GitHub
Actions. Proposed stack: Vite with plain TypeScript, MapLibre GL for the map,
Observable Plot for charts. Core views: national map by UAT, mayor-term page
(timeline planned → contracted → delivered → claimed, funds by source,
procurement risk, context panel), methodology, data downloads, corrections
form.
