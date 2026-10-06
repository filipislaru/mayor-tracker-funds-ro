---
name: handoff-report
description: Writes the structured handoff report handoff/Txxx.md at the end of a task, for review by the project's planning assistant. Use when a task is finished, blocked or abandoned.
---
 
# Handoff report
 
Write `handoff/Txxx.md` with exactly these sections. Be factual and specific: the reviewer has not seen your conversation. Paste real command output, not paraphrases. Keep the file under about 400 lines; truncate long outputs and say so.
 
```markdown
# Handoff — Txxx <title>
 
Date (UTC):
Branch / last commit: <branch> / <short hash>
Status: done | partially done | blocked
 
## Summary
3–6 sentences: what now exists, and anything the reviewer must know first.
 
## Acceptance criteria
- [x] criterion 1 — evidence: <test name / command / file>
- [ ] criterion 2 — not met because …
 
## Files changed
<output of `git diff --stat main...HEAD`>
 
## Commands run and results
<each command and its relevant output, including `uv run pytest` summary and `uv run ruff check .`>
 
## Data produced
For each output file: path, row count, column names and types, null counts per column, and the first 5 rows.
 
## Checks requested in the brief
Every number or diagnostic listed under "Checks to report in the handoff", one per line.
 
## Sources used
source_id, exact URL(s), retrieval timestamp, licence or terms noted, sha256 of raw files.
 
## Deviations from the brief
What you did differently and why. "None" if none.
 
## Blockers and open questions
Numbered. For each: what you found, what you need decided.
 
## Risks and suggestions
Anything that might bite later (data quality, scale, cost, legal), and suggested follow-up tasks.
```
 
Rules:
- Never claim a check passed without showing the evidence.
- If you used any assumption, list it under "Deviations".
- If any data in the outputs is synthetic, say so in the Summary in bold. (It should not be, outside tests/.)
