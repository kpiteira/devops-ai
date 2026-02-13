# Task Type Categories

Classify tasks by category to determine required integration and smoke tests. This prevents "components work but aren't connected" bugs.

## Category Identification

| Category | Indicators |
|----------|-----------|
| **Persistence** | DB, repository, store, save, table, migration |
| **Wiring/DI** | Factory, inject, singleton, `get_X_service()` |
| **State Machine** | Status, state, transition, phase, workflow |
| **Cross-Component** | Calls, integrates, sends to, receives from |
| **Background/Async** | Background task, worker, queue, async loop |
| **External** | Third-party API, gateway, external service |
| **Configuration** | Env var, config, setting, flag |
| **API Endpoint** | Endpoint, route, request, response |

Tasks often belong to multiple categories. Apply tests for all that match.

## Failure Modes

| Category | Key Failure Modes |
|----------|-------------------|
| **Persistence** | Not wired, wrong connection, transaction issues, schema mismatch |
| **Wiring/DI** | Missing injection, wrong type, stale singleton |
| **State Machine** | Missing transition, invalid transition allowed, state not persisted |
| **Cross-Component** | Contract mismatch, timing issues, error not propagated |
| **Background/Async** | Never starts, never stops, orphaned work, race conditions |
| **External** | Connection failure, auth failure, parsing errors, timeout handling |
| **Configuration** | Missing required, wrong type, invalid value |
| **API Endpoint** | Missing validation, wrong status code, state not actually changed |

## Required Tests

| Failure Mode | Test Type | Pattern |
|--------------|-----------|---------|
| Not wired | Wiring test | `assert get_{service}()._{dependency} is not None` |
| Missing transition | State coverage | Parameterized test for all valid transitions |
| Contract mismatch | Contract test | Capture and verify data between components |
| Never starts | Lifecycle test | `assert {task} is not None and not {task}.done()` |
| Connection failure | Connection test | Health check + error handling |
| Missing validation | Validation test | Test that endpoint returns 422 for invalid input |
| State not changed | DB verification | Query table directly after operation |

## Smoke Tests

| Category | Pattern |
|----------|---------|
| Persistence | Query table directly: `SELECT * FROM {table} LIMIT 1` |
| Wiring/DI | `get_{service}()._{dependency} is not None` |
| Background | Check logs for expected task messages |
| Configuration | `env | grep {VAR_NAME}` |
| API Endpoint | `curl -X {method} {endpoint}` then verify state |
