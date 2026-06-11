# Testing Taxonomy

Tests are classified by what they exercise and what they need to run.

## Classification

| Type | Directory | Speed | Dependencies | Runs in |
|------|-----------|-------|-------------|---------|
| Unit | tests/unit/ | <100ms each | None (no I/O; fakes at the seams) | Pre-commit, CI |
| Integration | tests/integration/ | <5s each | Real services | CI |
| E2E | tests/e2e/ | <30s each | Full running system | Milestone validation |

## Unit tests

Unit tests exercise behaviors through public surfaces, with the in-process stack running real. "Unit" is a speed-and-determinism contract (no I/O), not a one-class isolation rule — the `tdd` rule defines where the fake/real line lives. They must have:

- No network calls (no `socket.connect`, no HTTP requests)
- No subprocess spawning (no `subprocess.run` unless mocked)
- No Docker dependencies
- No file I/O outside `tmp_path`
- No database connections

A unit test that takes more than 1 second is probably misclassified — it likely has a hidden external dependency and belongs in `tests/integration/`.

## Integration tests

Integration tests exercise interactions between components with real services. They may use:

- Real database connections
- Real HTTP endpoints
- Docker containers (started by the test or pre-existing)
- Real file system operations

## E2E tests

E2E tests exercise the full system as a user would interact with it. They require:

- All infrastructure running (containers, databases, services)
- Real API calls producing real state changes
- Observable, verifiable outcomes

## When each type runs

- **Pre-commit hook:** Unit tests only (`make check` → quality + unit tests)
- **CI pipeline:** Unit + integration tests
- **Milestone validation:** All types including E2E

## Enforcement

Python projects can use a `tests/unit/conftest.py` guardrail that blocks `socket.socket.connect` in unit tests. If a unit test needs network access, it belongs in `tests/integration/`.

## Naming conventions

Test files mirror the source structure:
- `src/myapp/service.py` → `tests/unit/test_service.py`
- `src/myapp/cli/main.py` → `tests/unit/test_cli_main.py`
