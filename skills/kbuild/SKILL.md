---
name: kbuild
description: Execute tasks (TDD) and orchestrate milestones from implementation plans.
metadata:
  version: "0.1.0"
---

# Build Command

Execute implementation plan tasks using TDD, or orchestrate an entire milestone by sequencing tasks with verification between them.

## Modes

**Single task:**
```
/kbuild impl: <milestone-file> task: <task-id>
```

**Full milestone:**
```
/kbuild impl: <milestone-file>
```

In milestone mode, execute tasks sequentially. After each task: verify handoff updated, tests pass, quality checks pass, changes committed. Resume by reading the handoff file to find the first incomplete task.

---

## Context Document Resolution

Milestone files include frontmatter referencing design and architecture docs:

```markdown
---
design: docs/designs/feature/DESIGN.md
architecture: docs/designs/feature/ARCHITECTURE.md
---
```

Read these before starting work. If frontmatter is missing and no docs are passed as parameters, ask for them.

---

## Research First

Before writing any code:

1. Read the design and architecture docs — understand the intent
2. Read existing code being replaced or modified — understand what's there
3. Find patterns to follow — look at similar code in the codebase
4. Check the handoff file — read gotchas and patterns from previous tasks

If you discover something that contradicts the task's assumptions (files don't exist, patterns not found, code already fixed), stop and verify before proceeding. Double-check with alternative searches. If still unexpected, report it rather than guessing.

Output a brief summary (2-4 sentences): design intent, architecture approach, implementation approach.

---

## Code Samples Are Structure, Not Implementation

Implementation plans contain code samples that show patterns and wiring — not complete functionality. Your job is to understand the structure, read the existing code, and implement with full functionality. Copying code samples verbatim is transcription, not implementation.

---

## Task Types

- **CODING** — TDD required. Write tests first, then implementation, then refactor.
- **RESEARCH** — Investigation, analysis, documentation. No TDD.
- **MIXED** — Research first, then TDD for the implementation portion.
- **VALIDATION** — E2E test execution. Exercise real system flows, report results with evidence. See the `e2e-testing` rule for what "real E2E" means.

---

## Implementation (CODING Tasks)

Follow TDD — the `tdd` rule has the full cycle. Write failing tests first, implement minimally to pass them, then refactor.

After implementation, run quality gates — the `quality-gates` rule has the checklist.

If infrastructure is configured in project config, also run an integration smoke test: start the system, exercise the modified flow, check logs.

---

## Handoff (Every Task)

After every task, update the handoff document — the `handoffs` rule has the conventions.

This is the single most consistently useful artifact across sessions. Create `HANDOFF_<feature>.md` in the implementation plan directory if it doesn't exist.

---

## Milestone Completion Report

When all tasks in a milestone are done, produce this summary. This is an interface contract used for PR creation — do not skip it.

```markdown
## Milestone Complete: [Name]

**Tasks completed:** X.1 through X.N
**Quality gates:** All passed

### E2E Tests Performed

| Test | Steps | Result |
|------|-------|--------|
| [test-name] | N | PASSED/FAILED |

### Challenges & Solutions

| Task | Challenge | Solution |
|------|-----------|----------|
| X.Y | [what went wrong] | [how it was fixed] |

### Failed Tests (Not Due to This Work)

| Test | Failure | Status |
|------|---------|--------|
| [test] | [description] | Pre-existing / Flaky |
```

If no E2E tests in the milestone, state "No E2E tests in this milestone."
If no challenges, state "No significant challenges encountered."
If all test failures addressed, state "All test failures were addressed."

---

## Error Handling

If blocked: don't mark the task as complete. Document the blocker and ask for guidance.

If task instructions contradict this skill, follow the task instructions — tasks may have context requiring different approaches.
