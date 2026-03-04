# E2E Testing

Every milestone ends with a VALIDATION task that exercises the real system end-to-end. This is the primary defense against "unit tests pass but the system doesn't work."

## What "real E2E" means

E2E tests run against the actual system, not test doubles:

- Running infrastructure (containers, services, databases) — not mocked services
- Real API calls to actual endpoints — not unit test fixtures
- Actual state changes (database writes, file creation) — not in-memory state
- Observable outcomes (logs, API responses, DB queries) — not assertions on mocks

## When to run E2E tests

- At the end of every milestone (as the final VALIDATION task)
- Whenever a milestone changes how components interact
- When previous milestone E2E tests should be re-verified for regression

## What makes a valid validation

A validation that only checks "the code runs without crashing" is insufficient. Valid E2E tests exercise real operational flows:

| Insufficient | Valid |
|--------------|-------|
| "API imports without error" | "Feature completes and produces expected output" |
| "System starts" | "Workflow executes and produces verifiable results" |
| "No exceptions on startup" | "Full workflow completes with verifiable output" |

## Evidence

E2E test results should include concrete evidence: API responses, log excerpts, database state, or screenshots. "It worked" without evidence is not a test result.

## Per-project test catalog

The `/ke2e` skill and agents (ke2e-test-scout, ke2e-test-designer, ke2e-test-runner) provide the full E2E testing workflow. Test recipes live at `.claude/skills/ke2e/tests/` per project and grow organically as milestones are validated.

Before designing a new E2E test, the scout agent searches the catalog for existing recipes. When no match exists, the designer agent creates a new recipe. The runner agent executes recipes against the real sandbox and reports PASS/FAIL with evidence and failure categorization.

## Integration with milestones

The milestone completion report includes an E2E test table documenting what was tested, the steps executed, and the result. This is an interface contract — PR reviewers rely on it to understand what was validated.
