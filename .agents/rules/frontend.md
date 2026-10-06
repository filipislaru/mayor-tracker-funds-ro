---
trigger: glob
globs: "site/**"
description: "Rules for the public website: content integrity, language, accessibility and design."
---
 
# Website rules
 
## Content integrity
- The site renders only data exported by the pipeline (`data/export/`). No hand-written numbers in templates.
- Every fact about a project, contract or fund links to its source document or record.
- Statements about a named mayor show only items with `human_verified` status; everything else is shown as aggregate statistics or clearly labelled "unverified".
- Indicators are shown separately (delivery, claim accuracy, funds secured, procurement risk). No single combined score unless a decision in docs/DECISIONS.md introduces one.
- Never use the words "corrupt" or "corruption" about a person or institution. Use "risk indicator", "verified", "not found in records".
- Every mayor page shows context (alignment with central government, population, transfers received) next to performance indicators.
- Every page links to the methodology and to the corrections form.
## Language
- UI language and translation approach follow docs/DECISIONS.md (D006). Use plain, active-voice, sentence-case copy written for citizens and journalists, not developers.
## Quality floor
- Responsive down to 360 px wide; keyboard navigable with visible focus; colour contrast WCAG AA; respects prefers-reduced-motion; works without third-party trackers.
- Map and charts have text alternatives (a table or summary sentence).
## Design
- Ground visual choices in the subject: public money, local government, maps of Romania. Avoid templated defaults (identical rounded cards with soft shadows, all-caps eyebrow labels, gradient decoration).
- One or two typefaces chosen deliberately; full support for Romanian diacritics (ă â î ș ț) is mandatory.
- Spend boldness in one place (likely the map); keep everything else quiet and disciplined.
