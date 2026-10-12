# P01 — Probe: access to tender documentation and TED notice text

Status: done
Depends on: T001a
Branch: task/P01-tender-docs-probe

## Goal
Find out, with a small sample and no bulk downloading, whether the text needed for the "tailored tenders" measure can be obtained: (a) full tender documentation from SICAP (e-licitatie.ro), and (b) selection-criteria text in TED notices for Romanian local authorities. The output is a short written report, not a dataset.

## Questions to answer
1. SICAP: Are contract notices and their attached documents (fișa de date, caiet de sarcini, documentația de atribuire) publicly viewable without logging in? Is there an official API, open-data export or bulk download? What do robots.txt and the terms of use say about automated access?
2. TED: Is there an official API or bulk download for notices? For Romanian contract notices from local authorities (2020–2024), which fields hold selection/qualification criteria and technical requirements as text, and how long and detailed is that text typically?
3. Linkage: Can a TED notice be linked to its SICAP procedure (for example by procedure or notice number)?

## Method and limits
- Official documentation, APIs and public pages only, through the PoliteClient (robots.txt, rate limits). No logins, no CAPTCHAs, no TLS bypass, no circumventing any restriction. If access needs an account, stop and report.
- At most 20 notices in the sample, and at most 50 requests per host in total.
- Downloaded samples go to data/raw/ via the PoliteClient as usual (git-ignored). Never commit downloaded content.
- Anything not verified from a page or document you actually accessed must be labelled "unverified". Never reconstruct URLs or facts from memory.

## Deliverables
1. docs/probes/P01-tender-docs.md: findings per question, URLs of every page or document relied on, the sample (notice IDs), and a verdict for each route: feasible / feasible with limits / not feasible.
2. Any small scripts used, under pipeline/src/mayortracker/probes/ (not wired into the CLI).
3. handoff/P01.md.

## Acceptance criteria
- [ ] Each question answered with evidence links, or marked unanswered with the reason.
- [ ] Request counts per host reported.
- [ ] `uv run ruff check .` and `uv run pytest` pass.

## Out of scope
Building an ingestion pipeline, any LLM use, more than 20 notices.
