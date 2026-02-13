# Skills Modernization — Implementation Plan

## Milestone Summary

| # | Name | Tasks | Capability | Status |
|---|------|-------|------------|--------|
| M1 | Rules + Cleanup | 3 | Shared principles auto-load; old agents removed | -- |
| M2 | Slim Standalone Skills | 4 | kreview, kissue, kinfra-onboard trimmed and working with rules | -- |
| M3 | Merge Design Pipeline | 4 | /kdesign and /kplan replace 3 old skills | -- |
| M4 | Merge Execution Pipeline + Install | 4 | /kbuild replaces 2 old skills; install.sh updated | -- |

## Dependency Graph

```
M1 → M2 → M3 → M4
```

Linear chain — each milestone depends on the previous. M2 needs rules to exist. M3 needs the trimming pattern proven. M4 needs the design pipeline done to avoid interim skill references.

## Branch Strategy

Single branch: `impl/skills-modernization`

Commit per task. PR at end (or per-milestone if preferred). No sandbox/worktree needed — this is prompt engineering, not running code.

## Testing Approach

This project edits markdown skills and rules, not Python code. Verification is different:

- **Structural checks:** Files exist, symlinks correct, no residual boilerplate (grep), token counts
- **Functional checks:** Invoke skills on real problems (manual, in VALIDATION tasks)
- **No pytest** — there's no unit test for "does this skill produce good output"

Quality gates adapted: ruff/mypy only apply to install.sh changes (bash, so not applicable). The quality gate is structural correctness + token budget verification.

### Dogfooding Validation

The best test of a prompt engineering artifact is using it on real work. VALIDATION tasks in M3 and M4 include dogfooding — using the new skills on actual pending problems rather than just checking "does it load."

- **M3 (design pipeline):** Use /kdesign on a real upcoming feature to validate it produces good design artifacts
- **M4 (execution pipeline):** Use /kbuild on a real task to validate TDD flow and handoff output

Dogfooding catches issues that structural checks miss: awkward phrasing that confuses the model, missing context that a rule should provide, flow gaps that only surface during real use. If dogfooding reveals problems, fix the skill before removing the old version.

## Reference Documents

- Design: [DESIGN.md](../DESIGN.md)
- Architecture: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Intent: [INTENT.md](../INTENT.md)
