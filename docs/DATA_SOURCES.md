# Data source registry

Every record in the pipeline carries a `source_id` from this table. Agents may
update the **Status** column for sources a brief tells them to use; any other
change needs a brief.

Status values: `to verify` (believed to exist, not yet checked), `verified`
(accessed, format documented), `blocked` (problem recorded in a handoff),
`to request` (needs permission or contact), `deferred`.

| source_id | Source | Publisher | Used for | Coverage | Access and licence | Status |
|---|---|---|---|---|---|---|
| `siruta` | SIRUTA nomenclature of administrative units and localities | INS (National Institute of Statistics) | UAT and village reference table | current | Official file; locate current version | to verify |
| `lau_boundaries` | LAU boundaries | Eurostat GISCO | Map polygons; check that LAU codes match SIRUTA | recent years | Check licence and attribution terms | to verify |
| `aep_local` | Local election results | AEP (Permanent Electoral Authority) | Mayors, parties, votes, margins | 2008–2024 | Official results; format to document | to verify |
| `kohesio` | Kohesio projects and beneficiaries | European Commission (DG REGIO) | EU cohesion projects (ERDF, Cohesion Fund, ESF), 2014–2020; 2021–2027 being added | EU-wide | CSV/XLSX/RDF downloads; locations are sometimes the beneficiary's address | to verify |
| `eu_far` | EU Funds Absorbed by Romanian Municipalities, 2016–2022 (Marin & Glăvan) | UK Data Service | EU funds per UAT from budget execution | 2016–2022 | UKDS account; check licence | to verify |
| `budget_exec` | Local budget execution by UAT | MDLPA, Directorate for Local Fiscal and Budgetary Policies | Revenues, expenditures, EU funds, transfers | to check | to check | to verify |
| `opentender_ro` | OpenTender Romania (OCDS) | Government Transparency Institute | Procurement contracts and risk indicators | 2007–2024 | CC BY-NC-SA 4.0 (non-commercial) | to verify |
| `ted` | Tenders Electronic Daily | EU Publications Office | Above-threshold notices, incl. selection-criteria text | EU-wide | API and bulk downloads | to verify |
| `sicap` | SICAP / e-licitatie.ro | ADR | National procurement incl. tender documentation | 2018– | Bulk access uncertain | to verify |
| `efor_programmes` | PNDL and Anghel Saligny maps and databases | Expert Forum | National programme allocations by UAT | 2014– | Ask permission before reuse | to request |
| `art155_reports` | Mayors' annual reports (Art. 155, Administrative Code) | Each UAT website | Claimed achievements | 2020– | Public documents; polite crawling | to verify |
| `dev_strategies` | Local development strategies | UAT websites | Planned projects | varies | Public documents | to verify |
| `budget_investments` | Investment lists annexed to local budgets | UAT websites, Monitorul Oficial Local | Planned projects | varies | Public documents | to verify |
| `afir` | Rural development (PNDR) projects | AFIR | EAFRD-funded commune infrastructure | 2014– | to find | to verify |
| `pnrr` | Recovery and Resilience Plan contracts | MIPE | RRF-funded local projects | 2021– | to find | to verify |
| `ani_declarations` | Asset and interest declarations | ANI (National Integrity Agency) | Pre-office income, business ties | 2016– | Personal data; needs a dedicated task | deferred |
| `counties_iso` | County codes (ISO 3166-2:RO) | Compiled manually, verified by the user | County codes for display and CLI options | 41 counties + Bucharest | `config/counties.yaml` | to verify |
