# Working loop: Claude (planning and review) ↔ Antigravity (implementation)

This file is for Filip. The coding agent does not need to follow it.

## Roles

- **Claude, in the claude.ai Project**: architect and reviewer. Turns goals into
  task briefs, reviews what the agent produced, catches methodological and
  data-integrity problems, and drafts updates to SPEC, DECISIONS and TASKS.
- **Coding agent in Antigravity** (any model; a Gemini model makes the review
  more independent): implementer. Writes code and runs commands and tests
  inside the repository, following `AGENTS.md`, the rules in `.agents/rules/`
  and the skills in `.agents/skills/`.
- **You**: decision-maker and bridge. You approve plans, commit, and carry
  information between the two.

The repository is the single source of truth. Anything either assistant needs
to know beyond one conversation goes into a file in the repo.

## The loop (one task at a time)

1. **Pick the task (Claude).** Ask "what's next?" or describe what you want.
   Claude writes the brief `docs/tasks/Txxx-name.md`; save it into the repo and
   mark it `ready` in `docs/TASKS.md`.
2. **Start a fresh agent conversation (Antigravity).** One task per
   conversation keeps the agent's context clean. Use planning mode and prompt:

   > Execute the task in @docs/tasks/T001-repo-bootstrap.md using the
   > task-execution skill.

3. **Review the plan before approving.** Check it against the brief's
   acceptance criteria and "Out of scope" list. Push back if it proposes a
   source not in the brief, skips tests, or "uses sample data". If unsure,
   paste the plan to Claude.
4. **Let it implement and test.** Approve terminal commands as they come.
   Never accept a "fix" that weakens or deletes a failing test.
5. **Handoff.** The agent writes `handoff/Txxx.md` (handoff-report skill) and
   commits on `task/Txxx-...`.
6. **Review (Claude).** Bring one of:
   - the GitHub repo URL and branch name, if the repo is public. Claude can
     clone it, read the code and run the tests itself; or
   - the contents of `handoff/Txxx.md`, plus any files Claude asks for (paste
     or upload).
7. **Close or iterate.** Claude replies "accepted" or "changes needed". For
   changes, Claude writes a short follow-up brief (e.g. `T003a`). Merge into
   `main` only after acceptance, then update `docs/TASKS.md`.

## When something breaks, bring

- the exact command and the full error output (not a summary),
- what the agent already tried,
- `git status` and `git log --oneline -5`.

## Rules of thumb

- Keep tasks small: finishable in one sitting. If the agent's plan has more
  than about 8 steps, split the task.
- Never paste API keys into either chat. Keys live only in `.env`.
- If the agent says it "estimated", "assumed" or "used sample data" for real
  values, stop. That is how fabricated data gets in.
- Decisions are made with Claude and recorded in `docs/DECISIONS.md`, not made
  silently by the agent.
- The repo can be public for code; `data/` is git-ignored and never committed.

## Antigravity setup checklist

- Open the repository folder as the workspace.
- Agent side panel → … → Customizations: confirm `AGENTS.md`, the four rules
  in `.agents/rules/` and the two skills in `.agents/skills/` are listed. A
  rule file with missing or invalid frontmatter is silently ignored, so check
  all four appear.
- In agent settings, require your review before terminal commands run and
  before changes outside the workspace (exact setting names vary by version).
- Use planning mode for task work. Keep the same model for a task's whole
  conversation.
