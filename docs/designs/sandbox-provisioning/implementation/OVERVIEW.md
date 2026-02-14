# Sandbox Provisioning Implementation Plan

## Milestone Summary

| # | Name | Tasks | E2E Test | Status |
|---|------|-------|----------|--------|
| M1 | Provisioning pipeline | 4 | `kinfra impl` on khealth with secrets + config file, container starts healthy | - |
| M2 | Discovery | 3 | `kinfra init --check` detects undeclared env vars and gitignored mounts | - |

## Dependency Graph

```
M1 → M2
```

M1 delivers the provisioning runtime that M2's discovery populates config for.

## Branch Strategy

- M1: `impl/sandbox-provisioning-M1` from main
- M2: `impl/sandbox-provisioning-M2` from main (after M1 merged)

## Reference Documents

- Design: `../DESIGN.md`
- Architecture: `../ARCHITECTURE.md`
