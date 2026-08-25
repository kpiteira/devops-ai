# E2E Testing

Every milestone is gated by end-to-end evidence — the primary defense against "unit
tests pass but the system doesn't work." In the v2 contract that gate is the
milestone's planner-authored **acceptance tests** (the `test-quality` and
`testing-taxonomy` rules): real E2E runs against the brief's pinned surface, executed
in the executor's goal loop and on the milestone's PR.

## What "real E2E" means

E2E tests run against the actual system, not test doubles:

- Running infrastructure (containers, services, databases) — not mocked services
- Real API calls to actual endpoints — not unit test fixtures
- Actual state changes (database writes, file creation) — not in-memory state
- Observable outcomes (logs, API responses, DB queries) — not assertions on mocks

A test that mocks or seeds data without real calls is an integration test: write it if
useful, but it does not satisfy an E2E gate. "The system starts without crashing" is
not E2E evidence; "the workflow completes with verifiable output" is.

## Evidence

E2E results include concrete evidence: API responses, log excerpts, database state, or
screenshots. "It worked" without evidence is not a test result — a milestone PR carries
the blocking commands and their green output.

## The ke2e catalog

The `/ke2e` skill and agents (ke2e-test-scout, ke2e-test-designer, ke2e-test-runner)
remain the knowledge layer for E2E design and execution against project sandboxes:
recipes live at `.claude/skills/ke2e/tests/` per project, the scout searches before the
designer invents, the runner reports PASS/FAIL with evidence and failure
categorization. Planners can draw on the catalog when authoring acceptance tests;
executors can use the runner for exploratory validation beyond the blocking bar.

How the intent-level conformance review and this functional E2E pipeline fully compose
(ordering, shared artifacts, what blocks a feature boundary) is an open evolution —
`docs/EVOLUTIONS.md` item 2. Until it lands, the acceptance tests are the gate and the
catalog is a resource, not a required step.
