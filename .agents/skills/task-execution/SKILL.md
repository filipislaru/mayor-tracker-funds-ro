---
name: task-execution
description: Executes a task brief from docs/tasks/ end to end in this repository. Use whenever the user asks to execute, implement or work on a task file such as docs/tasks/T001-*.md.
---
 
# Task execution protocol
 
Follow these steps in order. Do not skip steps.
 
## 1. Load context
- Read the brief in full.
- Read AGENTS.md, and the sections of docs/SPEC.md, docs/ARCHITECTURE.md and docs/DATA_SOURCES.md that the brief references.
- Read any handoff files for tasks listed under "Depends on".
- Check `git status`. If the working tree is dirty, stop and ask the user.
## 2. Restate before planning
In the implementation plan, start with:
- the goal in one sentence,
- the acceptance criteria copied as a checklist,
- anything in the brief that is ambiguous or that you think is wrong, as explicit questions.
If any question blocks the work, ask the user and wait. Do not resolve it by assumption.
 
## 3. Plan
- List concrete steps (files to create or change, commands to run, tests to add).
- If the plan needs more than about 8 steps, propose splitting the task instead.
- Name every external source you will touch by its `source_id`. If you need a source that is not in the brief, stop and ask.
## 4. Implement
- Create the branch `task/Txxx-short-name` from the main branch.
- Work in small steps. After each meaningful step, run the relevant tests.
- Commit with messages starting `Txxx:`.
## 5. Verify
- Run `uv run ruff check .` and `uv run pytest`.
- Run the pipeline commands the brief specifies on real data where the brief requires it.
- Collect every number listed under "Checks to report in the handoff".
- Tick each acceptance criterion only if you have evidence (a command output, a file, a test). Unmet criteria stay unticked, with the reason.
## 6. Hand off
- Use the `handoff-report` skill to write `handoff/Txxx.md`.
- Update the task's status line in docs/TASKS.md to `in review`.
- Commit. Do not push or merge unless the user asks.
- End your turn with a short summary and the path of the handoff file.
## When things go wrong
- Source unreachable, format different from expected, licence unclear: stop, record what you found in the handoff under "Blockers", and end the task. Never substitute invented or sample data.
- A test fails and you cannot fix the underlying issue: leave it failing, explain it in the handoff.
- You realise the brief's approach is flawed: say so in the handoff with a proposed alternative. Do not implement the alternative without approval.
 
