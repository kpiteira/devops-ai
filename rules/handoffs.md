# Handoff Documents

After every task, update the handoff document so the next session (even if it's you) benefits from what you learned.

## Where

`HANDOFF_<feature>.md` in the implementation plan directory. Create it if it doesn't exist.

## What to include

- **Gotchas**: problem + symptom + solution (only if non-obvious)
- **Workarounds**: constraints you hit and how you worked around them
- **Emergent patterns**: architectural decisions made during implementation
- **Next task notes**: brief guidance for what's coming next

## What to exclude

- Task completion status (already in the plan)
- Process steps (already in the skill)
- Test counts or coverage numbers (observable by running tests)
- File listings (observable from the codebase)

## For VALIDATION tasks

Include E2E test name, steps executed, and result (PASSED/FAILED). E2E tests validate real system behavior — they're worth recording.

## Target size

Under 100 lines total for the entire handoff file. If it's getting long, trim older sections that are no longer useful.
