# E2E Testing Workflow

This file defines the end-to-end testing workflow using the three-agent system. It is loaded conditionally by ktask and kmilestone when E2E testing is configured in the project.

---

## When This Applies

This workflow applies when:
- The project has E2E testing configured in `.devops-ai/project.md` (under `E2E`)
- A task has type **VALIDATION**
- A milestone includes a validation task

If E2E testing is not configured, VALIDATION tasks should use the project's available testing commands and manual verification instead.

---

## The Three-Agent System

E2E tests use three specialized agents, each with a distinct role:

| Agent | Purpose | Model | When Used |
|-------|---------|-------|-----------|
| `e2e-test-designer` | Searches test catalog for existing tests, or hands off to architect | Fast (haiku) | Every validation |
| `e2e-test-architect` | Designs new test specifications with steps, criteria, and sanity checks | Thorough (opus) | When no existing test matches |
| `e2e-tester` | Executes tests against the real running system | Thorough (opus) | Every validation |

---

## Mandatory Workflow

### Step 1: Find or Design the Test

Invoke the `e2e-test-designer` agent:

```
Task(
    subagent_type="e2e-test-designer",
    prompt="Search for E2E tests covering [milestone capability].
    Validation requirements: [list what must work].
    Components involved: [list components]."
)
```

The designer searches the catalog at `.claude/skills/e2e-testing/tests/`.

**If match found:** Designer returns the test reference. Proceed to Step 3.

**If no match:** Designer returns "Architect Handoff Required" with context. Proceed to Step 2.

### Step 2: Design New Test (if needed)

Invoke the `e2e-test-architect` agent with the handoff context:

```
Task(
    subagent_type="e2e-test-architect",
    prompt="Design E2E test for [capability].
    Context from designer: [handoff context].
    The test should verify: [specific requirements]."
)
```

The architect:
- Designs the full test specification (steps, expected results, evidence to capture)
- Defines success criteria and sanity checks
- If the test is reusable, writes it to the catalog (`.claude/skills/e2e-testing/tests/[category]/[name].md`)
- If the test is a one-off, returns the spec for embedding in the milestone

### Step 3: Execute the Test

Invoke the `e2e-tester` agent:

```
Task(
    subagent_type="e2e-tester",
    prompt="Execute E2E test: [category]/[name].
    Test specification: [spec or catalog reference].
    System should be running at: [endpoints/ports]."
)
```

The tester:
- Runs preflight checks (is the system running? are prerequisites met?)
- Executes each test step against the real system
- Captures evidence (logs, API responses, state queries)
- Reports PASS/FAIL with evidence for each success criterion

### Step 4: Report Results

After execution, document:
- Test name and category
- Number of steps executed
- Result (PASSED/FAILED) for each success criterion
- Evidence captured
- Any failures with investigation notes

---

## What "Real E2E" Means

E2E tests must exercise the actual system, not test doubles:

| Real E2E | Not E2E |
|----------|---------|
| Running infrastructure (containers, services) | Mocked services |
| Real API calls to actual endpoints | Unit test fixtures |
| Actual state changes (database, files) | In-memory state |
| Observable outcomes (logs, responses, queries) | Assertions on mocks |

---

## Anti-Patterns

**NEVER do these:**
- Run bash commands from milestone files directly — use the agent workflow
- Write Python scripts to "test" the feature — use the tester agent
- Use curl commands without the e2e-tester agent context
- Call integration tests "E2E" — they test different things
- Skip the designer and go straight to running tests
- Accept "it starts without errors" as valid E2E — must verify real operational flows

---

## Valid vs Invalid Validation

| Invalid | Valid |
|---------|-------|
| "API imports without error" | "Feature completes and produces expected output" |
| "System starts" | "Workflow executes and produces verifiable results" |
| "No exceptions on startup" | "Full workflow completes with verifiable output" |

A validation that only checks "the code runs without crashing" will miss:
- Save/load bugs that only appear when data flows end-to-end
- Config mismatches between components
- Missing dependencies only needed at runtime

**If a milestone changes how components interact, the validation MUST exercise that interaction with real data.**

---

## Integration with ktask

When ktask encounters a VALIDATION task:
1. Load this E2E prompt
2. Follow Steps 1-4 above
3. Record results in the handoff document
4. Include test name, steps executed, and PASS/FAIL result

## Integration with kmilestone

When kmilestone encounters a VALIDATION task:
1. Include E2E reminder when invoking ktask
2. After ktask completes, capture E2E test results in tracking
3. Include all E2E results in the milestone completion summary table
