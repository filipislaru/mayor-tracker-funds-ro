# Spec — Romania Mayor Tracker (working title)

## Purpose

Give citizens, journalists and researchers a transparent, source-linked view
of what each Romanian mayor planned, claimed and verifiably delivered, what
funds they secured, and how risky their procurement looked. Then use the same
data for an academic paper on local governance, EU funds and political
economy in Romania.

## Unit of analysis

The **mayor-term**: one mayor in one administrative unit (UAT, identified by
its SIRUTA code) for one term of office.

## The four layers per mayor-term

1. **Planned**: projects in campaign programmes (where found), local
   development strategies and investment lists annexed to approved budgets.
2. **Claimed**: achievements listed in the mayor's annual report on the
   economic, social and environmental state of the UAT (Art. 155,
   Administrative Code, OUG 57/2019), published on the UAT's website.
3. **Verified**: independent records — procurement contracts, EU-funded
   projects (Kohesio; rural development; PNRR), national programmes (PNDL,
   Anghel Saligny); later, satellite verification of physical works.
4. **Integrity risk**: procurement red flags (single bidding and similar
   indicators), later a text-based measure of tailored tender requirements,
   and connections indicators.

## Indicators (shown separately, never combined into one score)

- **Delivery rate**: share of planned projects (by count and value) linked to
  a verified record.
- **Claim accuracy**: share of claimed achievements linked to an independent
  record.
- **Funds secured** per capita, by source.
- **Procurement integrity risk**: share of single-bid contracts and other
  documented red flags.
- **Context** shown alongside: alignment with central government, population,
  own revenues, discretionary transfers received.

Every indicator has a written definition and method version on the site's
methodology page.

## Principles

- **Provenance first**: every fact links to its source document.
- **No verdicts**: risk and performance indicators, never labels such as
  "corrupt".
- **Human verification** of anything shown about a named person.
- **Right of reply**: a visible corrections process for mayors and citizens.
- **Accuracy before coverage**: a correct pilot beats a national dataset full
  of errors.
- **Reproducibility**: the full dataset can be rebuilt from raw sources by
  running the pipeline.

## Minimum viable product

- National reference data: all UATs with boundaries; all mayoral election
  results for 2020 and 2024.
- One pilot county, term 2020–2024: all four layers, project linking, the
  indicators, and a working website (map, mayor pages, methodology,
  corrections form).

## Non-goals (for now)

- Social-media monitoring or reader comments.
- Asset and interest declarations (later, dedicated task with explicit field
  limits).
- County councils and county council presidents.
- Any composite "corruption score".
