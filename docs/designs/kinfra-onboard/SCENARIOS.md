# Design Validation: kinfra-onboard

**Date:** 2026-02-12
**Documents Validated:**
- Design: DESIGN.md
- Architecture: ARCHITECTURE.md

## Validation Summary

**Scenarios Validated:** 12 traced
**Critical Gaps Found:** 7 (all resolved)
**Interface Contracts:** kinfra init CLI flags, SKILL.md phases

## Key Decisions Made

1. **OTEL endpoint after onboarding:** Set app config to `http://localhost:44317` (shared stack host port). Sandbox overrides via env var. Apps with graceful degradation (like khealth) handle unreachable endpoints safely.
   - Context: GAP-1 — after commenting out local Jaeger, what endpoint to use?
   - Trade-off: Assumes shared observability stack is running for local dev tracing.

2. **kinfra init failure handling:** Skill reports the error, explains what went wrong, and makes a decision with the user. Does not silently work around kinfra.
   - Context: GAP-2 — what if kinfra init --dry-run or --auto fails?
   - Trade-off: User must be involved when things go wrong, no fully automated recovery.

3. **Rollback on verification failure:** Full rollback — restore compose from .bak, delete generated infra.toml, `git checkout` any skill-edited files. Commit hasn't happened yet so this is clean.
   - Context: GAP-3 — scope of undo if Phase 4 verification fails.

4. **Selective git staging:** Skill tracks which files it changed through Phase 3, stages only those files explicitly. Never uses `git add -A`.
   - Context: GAP-4 — dirty git + onboarding commit shouldn't capture unrelated changes.

5. **Re-onboarding:** `--auto` auto-confirms update on existing config. Compose rewriting already skips parameterized ports. Needs a test.
   - Context: GAP-5 — what happens when user re-runs on already-onboarded project.

6. **Don't edit Python source:** Skill updates config files (YAML, env, etc.) not hardcoded Python defaults. If OTEL is only in source code with no config mechanism, surface to user and discuss.
   - Context: GAP-6 — OTEL endpoint hardcoded in Python instead of config file.

7. **Health endpoint override flag:** Add `--health-endpoint` to `kinfra init` so `--auto` can pass the correct value detected by the skill, rather than always defaulting to `/api/v1/health`.
   - Context: GAP-7 — `--auto` default wrong for many projects.

## Interface Contracts

### kinfra init CLI (updated)

```
kinfra init [--dry-run] [--auto] [--health-endpoint TEXT]
```

| Flag | Behavior |
|------|----------|
| (none) | Current interactive mode, unchanged |
| `--dry-run` | Run full detection pipeline, print planned changes to stdout, write nothing |
| `--auto` | Accept all detected defaults, no prompts. Auto-confirm update if config exists. |
| `--dry-run --auto` | Preview with defaults, no prompts, write nothing |
| `--health-endpoint` | Override health endpoint (default: `/api/v1/health`). Useful with `--auto`. |

**--dry-run output format:**

```
Project: wellness-agent
Prefix: wellness-agent
Compose: docker-compose.yml

Services detected:
  wellness-agent: ports [8080]
  jaeger: ports [14686, 14317] (observability — will be commented out)

Planned infra.toml:
  [project]
  name = "wellness-agent"
  ...

Compose changes:
  - Parameterize port 8080 → ${WELLNESS_AGENT_WELLNESS_AGENT_PORT:-8080}
  - Comment out service: jaeger
  - Remove depends_on: jaeger from wellness-agent
  - Add kinfra header comment
  - Backup: docker-compose.yml.bak

No files written (dry run).
```

### Skill Phase Contracts

**Phase 1 output (to user):**
```
## Project Analysis

- **Project:** wellness-agent (from .devops-ai/project.md)
- **Git state:** Clean
- **Compose:** docker-compose.yml (2 services)
  - wellness-agent: port 8080, health check at /api/v1/health
  - jaeger: ports 14686, 14317 (observability — shared stack replaces this)
- **OTEL config:** config.yaml → endpoint: "http://jaeger:4317"
- **kinfra status:** Not onboarded (no infra.toml)
```

**Phase 2 output (to user):**
```
## Proposed Changes

**kinfra init will:**
[dry-run output from above]

**I will also:**
- Update config.yaml: OTEL endpoint → http://localhost:44317
- Update .devops-ai/project.md: Add Infrastructure section
- Update any docs/skills referencing local Jaeger ports

Proceed?
```

**Phase 3 tracked file list:**
```
Files changed:
- .devops-ai/infra.toml (created by kinfra init)
- docker-compose.yml (rewritten by kinfra init)
- docker-compose.yml.bak (backup, not committed)
- config.yaml (OTEL endpoint updated by skill)
- .devops-ai/project.md (Infrastructure section added by skill)
```

**Phase 4 verification checks:**
1. `.devops-ai/infra.toml` exists and parses as valid TOML with required fields
2. `docker compose config` succeeds (or: compose file parses as valid YAML)
3. OTEL endpoint references point to shared stack (no references to old local Jaeger)
4. On success: `git add <tracked files>` + `git commit`
5. On failure: restore .bak, delete infra.toml, `git checkout` edited files

## Recommended Milestone Structure

### Milestone 1: kinfra init --dry-run and --auto flags

**User Story:** A developer or script can run `kinfra init --dry-run --auto` to preview onboarding changes without interaction.

**Scope:**
- `init_cmd.py`: Refactor `init_command()` to separate detection from interaction from writing. Add `--dry-run`, `--auto`, and `--health-endpoint` flags.
- `main.py`: Wire flags through to `init_command()`.
- Tests: Unit tests for --dry-run (no files written), --auto (no prompts), combined mode.

**E2E Test:**
```
Given: A project directory with docker-compose.yml containing app + Jaeger services
When: kinfra init --dry-run --auto
Then: stdout shows planned infra.toml and compose changes, no files are created or modified
```

**Depends On:** Nothing

---

### Milestone 2: kinfra-onboard skill

**User Story:** A developer runs `/kinfra-onboard` in any project and gets a phased, intelligent onboarding experience.

**Scope:**
- `skills/kinfra-onboard/SKILL.md`: Full skill document with Phase 1-4 instructions, --check mode, error handling, OTEL rewiring guidance.
- Manual validation on khealth as the first real target.

**E2E Test:**
```
Given: khealth project (compose with app + Jaeger, OTEL config, clean git)
When: /kinfra-onboard
Then: All 4 phases complete — infra.toml created, compose rewritten, OTEL updated, project.md updated, git commit created
```

**Depends On:** Milestone 1 (skill calls kinfra init --dry-run --auto)
