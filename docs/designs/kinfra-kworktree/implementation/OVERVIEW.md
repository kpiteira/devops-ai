# kinfra + kworktree: Implementation Plan

## Milestone Summary

| # | Name | Tasks | E2E Test | Status |
|---|------|-------|----------|--------|
| M1 | Foundation | 7 | kinfra init → spec → done cycle | Pending |
| M2 | Sandbox Slots | 7 | kinfra impl → status → done with running sandbox | Pending |
| M3 | Shared Observability | 5 | Sandbox traces visible in shared Jaeger | Pending |
| M4 | Agent-deck + kworktree | 4 | --session creates agent-deck session + kworktree skill | Pending |

## Dependency Graph

```
M1 → M2 → M3
       ↘ M4
```

M3 and M4 are independent of each other (both depend on M2).

## Architecture Alignment

### Core Patterns

| Pattern | Implementing Tasks |
|---------|-------------------|
| Layered CLI (commands → modules → state) | 1.1, 1.4, 2.5, 2.6, 3.4, 4.2 |
| Config-driven adapter (infra.toml) | 1.2, 1.5, 1.6 |
| Global slot registry (JSON) | 2.2 |
| Compose override injection | 2.3 |
| Shared external network | 3.1, 3.2, 3.3 |
| Optional integration (agent-deck) | 4.1, 4.2 |

### Key Decisions Reflected in Tasks

| Decision | Task(s) |
|----------|---------|
| Absolute paths for compose invocations | 2.4, 2.5 |
| Compose file copied to slot dir for teardown safety | 2.3 |
| TCP bind test before slot allocation | 2.1 |
| Docker-style mount syntax in infra.toml | 1.2, 2.3 |
| Impl without infra.toml = worktree only (no error) | 2.5 |
| ruamel.yaml for comment-preserving YAML edits | 1.6 |

## Reference Documents

- Design: [DESIGN.md](../DESIGN.md)
- Architecture: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Validation: [SCENARIOS.md](../SCENARIOS.md)
