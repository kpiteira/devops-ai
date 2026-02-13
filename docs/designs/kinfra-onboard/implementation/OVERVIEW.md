# kinfra-onboard Implementation Plan

## Milestone Summary

| # | Name | Tasks | E2E Test | Status |
|---|------|-------|----------|--------|
| M1 | kinfra init --dry-run and --auto | 3 | `kinfra init --dry-run --auto` on test project, no files written | - |
| M2 | kinfra-onboard skill | 2 | `/kinfra-onboard` on khealth, full 4-phase flow | - |

## Dependency Graph

```
M1 → M2
```

M1 delivers the CLI flags that M2's skill depends on.

## Reference Documents

- Design: `../DESIGN.md`
- Architecture: `../ARCHITECTURE.md`
- Validation: `../SCENARIOS.md`
