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
- **VALIDATION** — Real E2E tests required against the running sandbox. Follow this sequence:
  0. **Discover the sandbox** — Run `kinfra status` to find the sandbox port and slot. If the sandbox is not running, run `kinfra sandbox start`. If code has changed since the sandbox was last built, run `kinfra sandbox rebuild` to update the container image. Do NOT skip this step or assume the sandbox is unavailable.
  1. Invoke the **ke2e-test-scout** agent with the milestone's validation requirements. The scout searches the ke2e test catalog (`.claude/skills/ke2e/tests/`) and returns matching recipes or hands off to **ke2e-test-designer** for new recipe creation.
  2. Invoke the **ke2e-test-runner** agent with the identified test recipes. The runner executes pre-flight checks, runs test steps against the sandbox, and reports PASS/FAIL with evidence and failure categorization.
  3. Do NOT write pytest code for E2E validation — use catalog recipes executed by the runner agent.
  4. If you catch yourself writing `@pytest.mark.mock` or seeding data instead of calling real services, stop: that is an integration test, not E2E.

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

**Before writing the report**, verify the E2E table by answering these questions for each test listed:
1. Did this test make real external calls (API, database, container)?
2. Did you actually run it with real credentials and see it pass?
3. If it uses `@pytest.mark.mock`, seeded data, or mocked externals — it is NOT E2E. Classify it as integration.

Tests that don't make real external calls MUST NOT appear in the E2E table. Put them in a separate "Integration Tests" section. Misclassifying integration tests as E2E is an untruthful report.

```markdown
## Milestone Complete: [Name]

**Tasks completed:** X.1 through X.N
**Quality gates:** All passed

### E2E Tests Performed
<!-- Every test here MUST have made real external calls -->
<!-- If a test uses mocks or seeded data, move it to Integration Tests -->

| Test | What it exercises (real calls to...) | Result |
|------|--------------------------------------|--------|
| [test-name] | [e.g. "real Anthropic API via op run"] | PASSED/FAILED |

### Integration Tests

| Test | Result |
|------|--------|
| [test-name] | PASSED/FAILED |

### Challenges & Solutions

| Task | Challenge | Solution |
|------|-----------|----------|
| X.Y | [what went wrong] | [how it was fixed] |

### Failed Tests (Not Due to This Work)

| Test | Failure | Status |
|------|---------|--------|
| [test] | [description] | Pre-existing / Flaky |

### E2E Catalog Tests Executed
<!-- Recipes from .claude/skills/ke2e/tests/ executed by ke2e-test-runner -->

| Recipe | Result | Category (if failed) |
|--------|--------|---------------------|
| [category/name] | PASSED/FAILED | [ENVIRONMENT/CONFIGURATION/CODE_BUG/TEST_ISSUE] |

### E2E Gate
<!-- This section is REQUIRED. If empty, the milestone is NOT complete. -->
- [ ] ke2e-test-scout invoked with milestone validation requirements
- [ ] ke2e-test-runner invoked with test recipes
- [ ] All recipes PASSED or failures categorized with remediation
- [ ] No ENVIRONMENT failures remaining (environment must be stable)
```

If no catalog recipes exist for this milestone's changes, invoke ke2e-test-scout to confirm and document the gap — do NOT simply state "No E2E tests."
If no integration tests, omit that section.
If no challenges, state "No significant challenges encountered."
If all test failures addressed, state "All test failures were addressed."

---

## Error Handling

If blocked: don't mark the task as complete. Document the blocker and ask for guidance.

If task instructions contradict this skill, follow the task instructions — tasks may have context requiring different approaches.
