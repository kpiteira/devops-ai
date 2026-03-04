---
name: ke2e
description: Knowledge base for E2E test design and execution against project sandboxes. Used by ke2e-test-scout (catalog lookup), ke2e-test-designer (new test design), and ke2e-test-runner (execution) agents.
metadata:
  version: "1.0.0"
---

# E2E Testing Skill

## Purpose

Knowledge base for E2E test design and execution. Used by:
- **ke2e-test-scout** agent — Fast catalog lookup during planning
- **ke2e-test-designer** agent — Design new tests when no match exists
- **ke2e-test-runner** agent — Execute tests and report results

## Agents

| Agent | Model | Purpose | When Invoked |
|-------|-------|---------|--------------|
| ke2e-test-scout | haiku | Find existing tests, identify gaps | During kbuild VALIDATION tasks |
| ke2e-test-designer | opus | Design new tests from scratch | When scout finds no match |
| ke2e-test-runner | sonnet | Execute tests, report results | After scout/designer identify tests |

## How Tests Are Designed

```
kbuild (VALIDATION task)
    |
    v
ke2e-test-scout (haiku) --- catalog lookup
    |
    +-- match found --> return recommendation
    |
    +-- no match --> ke2e-test-designer (opus)
                          |
                          v
                    new test recipe written to catalog
```

### ke2e-test-scout (haiku) - Catalog Lookup

1. Receives validation requirements from kbuild
2. Loads this skill's catalog
3. Searches for matching tests using category, capability, and keyword heuristics
4. Returns recommendations OR hands off to designer

### ke2e-test-designer (opus) - New Test Design

1. Receives handoff from scout when no match exists
2. Reads `.devops-ai/infra.toml` for sandbox configuration
3. Analyzes requirements deeply (edge cases, false positives, sanity checks)
4. Designs comprehensive test recipe using [TEMPLATE.md](TEMPLATE.md)
5. Writes reusable tests to `.claude/skills/ke2e/tests/{category}/{name}.md`

**Why two agents?** Catalog lookup is mechanical (haiku is fast/cheap). Designing new tests requires reasoning about validation, false positives, and edge cases (opus provides quality).

## How Tests Are Executed

The ke2e-test-runner agent:
1. Loads this skill (SKILL.md)
2. Finds requested tests in the catalog
3. Loads test recipe files
4. Runs pre-flight checks with cure loops
5. Executes test steps via curl and docker exec
6. Reports PASS/FAIL with evidence and failure categorization

## Test Catalog

Your project's catalog lives at `.claude/skills/ke2e/tests/`. Tests are added by the ke2e-test-designer agent and grow organically as milestones are validated.

**To populate:** When the scout finds no matching test, the designer creates one. Over time, the catalog covers the project's key user scenarios.

**Catalog structure:**
```
.claude/skills/ke2e/tests/
  <category>/
    <test-name>.md
```

Categories are project-specific (e.g., `workflow/`, `api/`, `infrastructure/`, `data-pipeline/`).

<!-- When tests exist, add a catalog table here:
| Test | Category | Duration | Use When |
|------|----------|----------|----------|
| category/name | Category | ~Xs | Description |
-->

## Pre-Flight Modules

| Module | Checks | Used By |
|--------|--------|---------|
| [common](preflight/common.md) | Docker, sandbox port, API health | All tests |

Project-specific preflight modules can be added to `.claude/skills/ke2e/preflight/` (e.g., for checking external service connectivity, database readiness, or session warmup).

## Troubleshooting

| Domain | Module | Common Issues |
|--------|--------|---------------|
| [Common](troubleshooting/common.md) | General | Timeouts, cold start, schema changes, port confusion |

## Creating New Tests

Use [TEMPLATE.md](TEMPLATE.md) when creating new test recipes. See [FAILURE_CATEGORIES.md](FAILURE_CATEGORIES.md) for categorizing failures.

## What "Real E2E" Means

E2E tests make real calls against a running sandbox container. Not mocked. Not "integration with mocks."

- Real API calls to container endpoints (curl, httpx)
- Real processing inside the container
- Real state changes observed via docker exec or API response
- Observable outcomes asserted on real data

Integration tests with mocked externals are NOT E2E. Never label them as such.

## Sandbox Configuration

E2E tests run against a kinfra-managed sandbox. Configuration comes from `.devops-ai/infra.toml`:

```toml
[sandbox.ports]
API_PORT = 8000              # Port variable name and default

[sandbox.health]
endpoint = "/health"         # Health check path
port_var = "API_PORT"        # Which port var to use for health checks
```

```bash
# Find your sandbox
kinfra status

# Start/rebuild sandbox
kinfra sandbox start

# Run tests (set port var to sandbox port, not production)
<PORT_VAR>=<sandbox_port> ke2e-test-runner <test-name>
```

**Never test against the production port.** Sandbox port = base + slot_id (e.g., 8000 + 1 = 8001).
