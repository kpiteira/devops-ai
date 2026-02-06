---
name: ktask
description: Implement tasks from implementation plans using TDD methodology with structured verification.
metadata:
  version: "0.1.0"
---

# Task Implementation Command

Implements tasks from a vertical implementation plan using TDD methodology.

This command embodies partnership values — craftsmanship over completion, honesty over confidence, decisions made together.

---

## Configuration Loading

**FIRST STEP — Do this before any workflow action.**

1. Read `.devops-ai/project.md` from the project root
2. If the file exists, extract:
   - **Project.name** — used in context and reporting
   - **Testing.unit_tests** — command to run unit tests (e.g., `make test-unit`, `pytest tests/unit`)
   - **Testing.quality_checks** — command to run quality checks (e.g., `make quality`, `ruff check .`)
   - **Infrastructure.start** — command to start infrastructure (e.g., `docker compose up -d`)
   - **Infrastructure.logs** — command to check logs (e.g., `docker compose logs backend --since 5m`)
   - **E2E.enabled** — whether E2E testing is configured
   - If essential values (Testing.*) are missing or say "Not configured": ask for them
   - If optional values (Infrastructure, E2E) are missing or say "Not configured": skip those sections silently — note briefly what was skipped
   - Do NOT offer to update the config file unless the user asks
3. If the file does NOT exist:
   - Ask: "What command runs your unit tests?" (default: `pytest tests/`)
   - Ask: "What command runs quality checks?" (default: none)
   - Ask: "Does this project use infrastructure (Docker, databases, etc.)?" (default: no)
   - Note: If no infrastructure, integration smoke test and E2E sections will be skipped.
   - Proceed with answers
   - Suggest: "Would you like me to create a `.devops-ai/project.md` so future sessions pick up these values automatically?"
4. Use the configured values throughout this workflow

### Generating Config (if user accepts)

If the user wants to create a config file:

1. **Inspect the project root** for project type indicators:
   - `pyproject.toml` → Python (extract project name, look for test commands in `[tool.pytest]`, `[tool.ruff]`)
   - `package.json` → Node/TypeScript (extract `name`, `scripts.test`, `scripts.lint`)
   - `Makefile` → Look for `test`, `quality`, `lint`, `check` targets
   - `go.mod` → Go (extract module name)
   - `Cargo.toml` → Rust (extract `[package].name`)
2. **Pre-fill values** from what you found (project name, test commands, quality commands)
3. **Show the draft config** to the user and ask them to confirm or adjust
4. **Write** `.devops-ai/project.md` using the template structure from `templates/project-config.md`

---

## Command Usage

```
/ktask impl: <plan.md> task: <task-id> [design: <design.md>] [arch: <architecture.md>]
```

**Required:**
- `impl:` — Implementation plan (from `/kdesign-impl-plan`)
- `task:` — Task ID, milestone, or range (e.g., "M1", "2.3", "Phase 2")

**Optional:**
- `design:` — Design document (overrides frontmatter)
- `arch:` — Architecture document (overrides frontmatter)
- Additional reference docs as needed

### Context Document Resolution

The command automatically discovers design/architecture docs:

1. **Parse frontmatter** from the implementation plan file
2. **If frontmatter has refs** → use them automatically
3. **If CLI params provided** → they override frontmatter
4. **If neither** → fail with: "No design/architecture docs found. Add frontmatter to plan or pass design:/arch: params"

**Frontmatter example** (in milestone file):

```markdown
---
design: docs/designs/feature-name/DESIGN.md
architecture: docs/designs/feature-name/ARCHITECTURE.md
---
```

---

## Workflow Overview

```
1. Setup       → Retrieve task, verify branch, classify type
2. Research    → Read docs, check handoffs, summarize approach
3. Implement   → TDD cycle (CODING tasks) or E2E execution (VALIDATION tasks)
4. Verify      → Acceptance criteria, quality gates
5. Complete    → HANDOFF UPDATE (MANDATORY), task summary
```

**Handoff updates are MANDATORY** after every task (not just milestones).

---

## Code Samples Are Structure, Not Implementation

**Implementation plans contain code samples. These show patterns and wiring — not complete functionality.**

When you see code in a plan, your job is to:
1. Understand the *structure* it demonstrates
2. Read the *existing code* (if replacing something) to understand what functionality exists
3. Implement the new structure with full functionality

If the code sample looks simpler than the existing code, that's expected — the sample shows skeleton, you provide the meat.

**Copying code samples verbatim is not implementation. It's transcription.**

---

## 1. Setup

### Retrieve Task

Extract the task from the implementation plan. Display:

- Task title and description
- Acceptance criteria
- Files to create/modify (for CODING tasks)
- E2E test reference (for VALIDATION tasks)

If validation output is provided, review key decisions to ensure consistency with resolved gaps.

### Verify Branch

Check task description for branch instructions:
- "Create new branch: [name]"
- "Work on branch: [name]"
- "Branch strategy: [description]"

If no branch strategy is specified, ask before proceeding.

### Classify Task Type

State the classification explicitly:

- **CODING** — Implementation work. TDD is required.
- **RESEARCH** — Investigation, analysis, documentation. No TDD.
- **MIXED** — Research first, then TDD for implementation portion.
- **VALIDATION** — E2E test execution. Run the test, report results.

### Check Handoffs

Look for `HANDOFF_*.md` in the implementation plan directory. If present, read and note:
- Critical gotchas from previous tasks
- Emergent patterns to follow
- Workarounds for known issues

---

## 2. Research Phase (All Tasks)

Before writing any code:

1. **Read context documents** — Design doc and architecture doc (from frontmatter or params), relevant sections of implementation plan
2. **Read code being replaced** — If this task replaces or restructures existing code, read it first. Understand what functionality exists before you design anything.
3. **Identify patterns to follow** — Find similar code in the codebase for style and conventions
4. **Locate dependencies** — Files, classes, functions that will be involved
5. **Note integration points** — How this task connects to other components

**Output:** Brief summary (2-4 sentences) covering:
- Design intent
- Architecture approach
- Implementation approach

Do not write implementation code during this phase.

### Guardrail: Unexpected Findings

If you discover something that contradicts the task's assumptions, **stop and verify before proceeding**.

Examples:
- Files mentioned in the task don't exist
- Patterns the task says to remove aren't found
- Code appears to already be fixed
- Search returns unexpected results
- Anything that seems odd or doesn't match expectations

**When this happens:**

1. **Double-check with alternative methods** — Try different glob patterns, grep variations, or broader searches
2. **If still unexpected, escalate**: Report to user/orchestrator before proceeding. Example: "Task says to fix ValueError in 8 indicator files, but I only found 4 files and none have ValueError. Should I proceed or investigate further?"

**Why this matters:** Research errors are silent and dangerous. A wrong conclusion like "files don't exist" leads to skipped work. Always verify unexpected findings.

---

## 3. Implementation (Coding Tasks Only)

Follow the TDD cycle: **RED → GREEN → REFACTOR**

### RED: Write Failing Tests

Before any implementation:

1. Create test file(s) following project conventions
2. Write tests covering:
   - Happy path (normal operation)
   - Error cases (failures, exceptions)
   - Edge cases (boundaries, null values)
3. Run tests using the configured unit test command
4. Verify tests fail meaningfully (not import errors)

Show output: "Tests written and failing as expected"

If you catch yourself writing implementation before tests, stop, delete the implementation code, and return to this phase.

### GREEN: Minimal Implementation

1. Write just enough code to make tests pass
2. Follow existing patterns in the codebase
3. Run tests frequently during implementation
4. Don't over-engineer or add untested features

Show output: "All tests passing"

### REFACTOR: Improve Quality

1. Improve code clarity and maintainability
2. Extract common patterns
3. Add documentation and type hints
4. Run tests after each refactoring
5. Run quality checks if configured

Show output: "Tests and quality checks passing"

---

## 4. Verification

### Integration Smoke Test (CODING tasks)

**If infrastructure is configured in project config:**

Unit tests verify components in isolation. Integration tests verify they work together. Passing unit tests does not mean the system works.

After unit tests pass (for changes affecting system behavior):

1. **Start system** using the configured infrastructure start command
2. **Execute modified flow**: Use CLI commands or API calls appropriate to the project
3. **Verify end-to-end**: Does the operation complete? Is state consistent?
4. **Check logs** using the configured infrastructure logs command
5. **Report**: "Integration test passed" or "Issue found: [description]"

**Skip integration testing for:**

- Pure refactoring with no behavior change
- Documentation-only changes
- Test-only changes

If integration test fails, investigate and fix before proceeding. The issue is likely architectural, not just code.

**If infrastructure is NOT configured:** Skip this section. Unit tests and quality checks are the verification layer.

### E2E Test Execution (VALIDATION tasks)

**If E2E testing is configured in project config**, also read `skills/shared/e2e-prompt.md` for the full E2E workflow instructions.

For tasks with type VALIDATION, this IS the implementation step.

---

**CRITICAL: E2E Tests MUST Use the Agent System**

**NEVER** write or run ad-hoc E2E tests. **ALWAYS** use the e2e agent workflow:

```
e2e-test-designer → (finds existing OR hands off to) → e2e-test-architect → e2e-tester
```

**Why this matters:**
- Ad-hoc tests often test components in isolation, not the real integrated system
- Ad-hoc tests frequently use shortcuts that don't validate actual platform behavior
- The agent system ensures tests run against the real platform with proper setup/teardown
- The agent system produces reproducible tests saved to the catalog for future use

**What "real E2E" means:**
- Running infrastructure (not mocked services)
- Real API calls (not unit test fixtures)
- Actual state changes (not in-memory)
- Observable outcomes (logs, API responses, queries)

---

**Mandatory Workflow:**

1. **Find or design the test** — Use `e2e-test-designer` agent:
   ```
   Task(subagent_type="e2e-test-designer", prompt="Search for E2E tests covering [milestone capability]...")
   ```
   - Designer searches the catalog at `.claude/skills/e2e-testing/tests/`
   - If match found: Returns test reference to execute
   - If no match: Returns "Architect Handoff Required" with context

2. **If new test needed** — Use `e2e-test-architect` agent:
   ```
   Task(subagent_type="e2e-test-architect", prompt="Design E2E test for [capability]. Context from designer: ...")
   ```
   - Architect designs full test specification
   - Architect writes test to catalog (`.claude/skills/e2e-testing/tests/[category]/[name].md`)
   - Returns test spec for execution

3. **Execute the test** — Use `e2e-tester` agent:
   ```
   Task(subagent_type="e2e-tester", prompt="Execute E2E test: [category]/[name] ...")
   ```
   - Tester runs preflight checks
   - Tester executes test steps against real platform
   - Tester reports PASS/FAIL with evidence

4. **Report results**: Document pass/fail for each success criterion

5. **Fix failures**: If E2E tests fail, investigate — the issue is in previously implemented tasks

**Anti-patterns (NEVER do these):**
- Running bash commands from the milestone file directly
- Writing Python scripts to "test" the feature
- Using curl commands without the e2e-tester agent context
- Calling integration tests "E2E" — they're different
- Skipping the designer and going straight to running tests

**If E2E testing is NOT configured:** VALIDATION tasks should verify functionality through the project's available testing commands and manual verification steps.

### Acceptance Criteria Validation

Go back to the task description. For each acceptance criterion:

1. Identify the type (feature, unit test, integration test, performance, documentation)
2. Validate it appropriately
3. Check it off with status

```markdown
- [x] Acceptance criterion 1 — VALIDATED
- [x] Acceptance criterion 2 — VALIDATED
- [ ] Acceptance criterion 3 — NOT MET (needs: ...)
```

If any criterion is not met, continue working before proceeding.

### Quality Gates

All must pass before completion:

- [ ] All unit tests pass (run configured unit test command)
- [ ] Quality checks pass (run configured quality command, if configured)
- [ ] E2E test passed (VALIDATION tasks, if E2E is configured)
- [ ] Code is documented (docstrings explaining "why")
- [ ] All work is committed with clear messages
- [ ] No security vulnerabilities introduced
- [ ] **Handoff document updated** (EVERY task - see Completion section)

---

## 5. Completion

### Handoff Document (MANDATORY - DO THIS FIRST)

**REQUIRED AFTER EVERY TASK**: You MUST update the handoff document before writing the task summary.

**Action steps:**

1. **Locate handoff file**: `HANDOFF_<phase/feature>.md` in the implementation plan directory
   - If it doesn't exist, CREATE it

2. **Add section for this task**: Add a new section titled `## Task X.Y Complete: [Task Name]`

3. **Document learnings** (only if it saves time for next implementer):
   - **Gotchas**: Problem + symptom + solution
   - **Workarounds**: Non-obvious solutions to constraints
   - **Emergent patterns**: Architectural decisions made during implementation
   - **Implementation notes**: Key patterns or approaches that worked well

4. **Add "Next Task Notes"**: Brief guidance for the next task (what files to import, what to watch out for)

**EXCLUDE** (wastes tokens):
- Task completion status (already in plan)
- Process steps (already in this command)
- Unit test counts or coverage numbers (observable from running tests)
- File listings (observable from codebase)

**INCLUDE for VALIDATION tasks:**
- E2E test name and result (PASSED/FAILED)
- Number of steps executed
- Any failure details or investigation notes

E2E tests are significant outcomes — they validate real system behavior, not just code correctness. Record them in the handoff so kmilestone can aggregate them into the milestone report.

**Target size**: Under 100 lines total for the entire handoff file.

**Why this matters**: You consistently find handoff documents useful when starting tasks. Creating them ensures the next task (even if it's you in a new session) benefits from your learnings.

### Task Summary

Provide a summary of what was accomplished:

```markdown
## Task Complete: [Task ID]

**What was implemented:**
- [Brief description of the change]

**Files changed:**
- [List of files created/modified/deleted]

**Key decisions made:**
- [Any non-obvious choices and why]

**Issues encountered:**
- [Problems hit and how they were resolved, or "None"]
```

This summary is displayed to the human (or orchestrator) and provides visibility into what happened during the task.

**Note:** PR creation is handled at milestone level, not per-task. Commits should be made after each task, but PRs are created when the full milestone is complete.

---

## Error Handling

If you encounter blockers:

- Do not mark task as complete
- Keep task in "doing" status
- Document the blocker
- Ask for guidance on how to proceed

---

## Task Instructions Override

If task-specific instructions contradict this command, follow the task instructions. Tasks may have context that requires different approaches.

---

## Project-Specific Test Patterns

Some projects have specific test patterns (e.g., custom test runners, fixtures that handle output formatting, framework-specific test helpers). These belong in the project's `.devops-ai/project.md` under `Project-Specific Patterns`, not in this skill.

When implementing tests, check the project config for any project-specific patterns before writing test code.

---

## Quick Reference

| Phase | Key Actions | Output |
|-------|-------------|--------|
| Setup | Retrieve, branch, classify, handoffs | Task details displayed |
| Research | Read docs, find patterns | 2-4 sentence summary |
| RED | Write tests, run, verify fail (CODING) | "Tests failing as expected" |
| GREEN | Implement, run tests (CODING) | "All tests passing" |
| REFACTOR | Clean up, quality checks (CODING) | "Tests and quality passing" |
| E2E | Run milestone E2E scenario (VALIDATION) | "E2E test passed" |
| Integration | Start system, execute flow, check logs | "Integration passed" |
| Acceptance | Validate each criterion | Checklist with status |
| Quality | Tests, quality, commits | All gates passed |
| **Handoff** | **Update HANDOFF_*.md (EVERY task)** | **Section added to handoff** |
| Summary | Write task completion summary | Task summary with changes/decisions |
