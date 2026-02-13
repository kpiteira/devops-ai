# kinfra-onboard: Design

## Problem Statement

Onboarding a project to the kinfra ecosystem (sandbox isolation, shared observability) requires understanding the project's current setup, making judgment calls about what's safe to change, running `kinfra init`, and then adapting app-level configuration that kinfra can't touch. Today this is a manual, project-specific process that requires knowing both kinfra internals and the target project's architecture.

## Goals

- A developer can run `/kinfra-onboard` in any project and get an intelligent, phased onboarding experience
- The skill assesses project readiness and safety before making changes
- The deterministic work (compose parameterization, config generation) stays in `kinfra init`
- The adaptive work (OTEL rewiring, app config changes, documentation updates) is handled by the skill with project-specific understanding
- The user approves each phase before the skill proceeds

## Non-Goals (Out of Scope)

- Replacing `kinfra init` — it remains a standalone CLI tool humans can run directly
- Handling production deployments or CI/CD changes
- Onboarding projects that don't use Docker Compose at all (kinfra requires it)
- Auto-fixing broken Docker setups — the skill assesses and reports, doesn't repair unrelated issues

## User Experience

### Scenario 1: Fresh project with local observability (khealth)

User runs `/kinfra-onboard` in a project that has a docker-compose.yml with app services and a local Jaeger instance. The skill:

1. **Phase 1 — Analyze:** Reads compose, app config, project.md. Reports what it found: "wellness-agent on port 8080, local Jaeger on 14686/14317, OTEL configured in config.yaml pointing to http://jaeger:4317. Git is clean."
2. **Phase 2 — Propose:** "I'll run `kinfra init --dry-run` to preview compose changes, then show you what app config needs updating." Shows the dry-run output and its own plan for OTEL rewiring. User approves.
3. **Phase 3 — Execute:** Runs `kinfra init --auto`, updates the app's OTEL endpoint config to use the shared stack, updates relevant docs/skills. Reports what changed.
4. **Phase 4 — Verify:** Confirms `infra.toml` is valid, compose still parses, app config is consistent.

### Scenario 2: Project already onboarded

User runs `/kinfra-onboard` in a project that already has `.devops-ai/infra.toml` and a kinfra-managed compose file. The skill detects this and reports: "This project is already onboarded to kinfra. Config looks current. Nothing to do." Offers to re-run analysis if the user suspects drift.

### Scenario 3: Project with no compose file

User runs `/kinfra-onboard` in a project with no Docker infrastructure. The skill reports: "No docker-compose.yml found. kinfra requires Docker Compose for sandbox management. You can still use kinfra for worktree management (spec/impl) without sandboxes." Offers to generate a minimal `infra.toml` with `has_sandbox = false`.

### Scenario 4: Dirty git state

User runs `/kinfra-onboard` in a project with uncommitted changes. The skill warns: "There are uncommitted changes. Onboarding modifies docker-compose.yml and possibly app config files. I recommend committing or stashing first so changes are easy to review and revert." Pauses for user decision.

### Scenario 5: Complex compose with non-standard observability

User runs `/kinfra-onboard` in a project that has a custom Prometheus config, Grafana dashboards, or an observability setup that doesn't match the standard image patterns. The skill identifies what it recognizes and what it doesn't, surfaces uncertainty: "I see a `monitoring` service using `prom/prometheus` — that matches kinfra's shared stack. But there's also a `metrics-collector` service I can't classify. Want me to treat it as an app service (keep it) or observability (comment it out)?"

## Key Decisions

### Decision 1: Skill drives kinfra, not the other way around
**Choice:** The skill is the intelligent orchestrator; `kinfra init` is the mechanical tool it calls.
**Alternatives considered:** Making kinfra init smarter itself; having the skill bypass kinfra entirely.
**Rationale:** Clean separation — kinfra stays deterministic and testable, the skill provides the judgment layer. Humans can still use `kinfra init` directly.

### Decision 2: Phased execution with user checkpoints
**Choice:** Four phases (Analyze, Propose, Execute, Verify) with user approval between Propose and Execute.
**Alternatives considered:** Single-pass execution; fully interactive question-by-question flow.
**Rationale:** Onboarding is a trust-building moment. Users want to see what will happen before it happens, but don't want to answer 15 individual questions.

### Decision 3: kinfra init gets --dry-run and --auto flags
**Choice:** Add `--dry-run` (preview without writing) and `--auto` (accept all defaults, non-interactive) to `kinfra init`.
**Alternatives considered:** Having the skill call kinfra's Python functions directly; generating infra.toml from the skill.
**Rationale:** `--dry-run` lets the skill preview and present changes. `--auto` lets it execute without interactive prompts. Both flags are useful for humans too. kinfra stays the single owner of compose rewriting logic.

### Decision 4: The skill handles app-level OTEL rewiring
**Choice:** The skill reads and modifies app config (e.g., config.yaml OTEL endpoint) to point at the shared stack.
**Alternatives considered:** Having kinfra handle this via infra.toml; leaving it as a manual step.
**Rationale:** OTEL config varies widely across projects (YAML config, env vars, code constants). An LLM skill can understand and adapt to any format. kinfra can't reasonably handle this generically.

### Decision 5: Safety assessment before any changes
**Choice:** The skill checks git state, compose validity, and existing kinfra config before proposing changes.
**Alternatives considered:** Just running kinfra init and handling errors.
**Rationale:** It's better to surface problems before making changes than to roll back after. The backup (.yml.bak) is a safety net, not the primary strategy.

### Decision 6: Update project.md after onboarding
**Choice:** Yes — the skill updates `.devops-ai/project.md` to add/update the Infrastructure section with kinfra commands.
**Rationale:** Keeps project.md as the single source of truth for how to work with the project. Other skills (ktask, kmilestone) read Infrastructure config from there.

### Decision 7: Support --check mode
**Choice:** `/kinfra-onboard --check` runs Phase 1 (Analyze) only and reports status without proposing changes.
**Rationale:** Useful for verifying onboarding state, detecting drift, or just understanding a project's current setup before committing to changes.

### Decision 8: Git commit after onboarding
**Choice:** Yes — the skill creates a commit with all onboarding changes after successful execution.
**Rationale:** Makes the onboarding a single, reviewable, revertable unit of change. The commit happens after verification, so it only captures a known-good state.

## Open Questions

- How should the skill handle projects that use `docker compose` profiles (e.g., `--profile observability`)? Defer until encountered.
