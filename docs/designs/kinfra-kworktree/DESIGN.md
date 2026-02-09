# kinfra + kworktree: Design

## Problem Statement

Developers using devops-ai skills can design, plan, and implement features — but launching isolated development environments (worktrees + infrastructure) requires either manual setup or project-specific tooling like ktrdr's kinfra CLI. There's no generic way to get the "one command creates a worktree, starts an isolated sandbox, and optionally launches an autonomous agent session" workflow across projects of varying complexity.

The core tension: the worktree + agent-deck orchestration is generic, but the infrastructure underneath (what Docker services to run, what ports to allocate, what health checks to perform, what directories to mount) is inherently project-specific.

## Goals

1. **Any project can use sandboxed worktrees with minimal setup** — from worktree-only (no Docker) to complex multi-service stacks
2. **A robust CLI (`kinfra`)** as part of devops-ai handles generic infrastructure: worktree lifecycle, port isolation, slot registry, health gating, agent-deck integration
3. **Projects declare their infrastructure via a simple adapter config** (`.devops-ai/infra.toml`) — no project-side code needed
4. **Guided setup** — `kinfra init` inspects the project, asks a few questions, generates config, and parameterizes the compose file
5. **Shared observability** — one always-running Jaeger + Grafana + Prometheus instance serves all sandboxes, with per-project/slot namespacing via OTEL resource attributes
6. **Agent-deck is optional** — the core worktree + sandbox workflow works without it; agent-deck adds session management when available
7. **A `kworktree` skill** provides the conversational interface, wrapping kinfra commands for use inside AI coding tools

## Non-Goals

- **Not replacing ktrdr's kinfra** — ktrdr keeps its own kinfra, its own sandboxes, its own observability stack, untouched. When ktrdr is ready to migrate, it can do so on its own terms. devops-ai's kinfra is designed so projects *could* adopt it, but nothing is forced.
- **Not managing production deployments** — this is dev/test infrastructure only
- **Not building a Docker orchestration framework** — we generate overrides and call `docker compose`; we don't abstract away Docker
- **Not requiring agent-deck** — it's a convenience layer, not a dependency
- **Not pre-provisioning slots by default** — on-demand slot creation is simpler and sufficient for most projects

## User Experience

### Scenario 1: First-time setup (khealth — simple project)

```
$ cd ~/Documents/dev/khealth
$ kinfra init

Inspecting project...
  Found: docker-compose.yml (2 services: wellness-agent, jaeger)
  Found: Python project (pyproject.toml)
  Found: .devops-ai/project.md (name: wellness-agent)

Services and ports detected:
  wellness-agent: 8080 (API)
  jaeger: 16686 (UI), 4317 (OTLP)

? Which service is your main application? [wellness-agent]
? Health check endpoint? [/api/v1/health]
? Which directories contain your code? [src/, tests/]

Note: Jaeger will be provided by kinfra's shared observability stack.
Commenting out jaeger service in docker-compose.yml (with explanation).

Generated: .devops-ai/infra.toml (12 lines)
Updated:  docker-compose.yml (ports parameterized with env vars)

Ready! Try: kinfra spec my-feature
```

### Scenario 2: Spec worktree (design work, no Docker)

```
$ kinfra spec wellness-reminders

Created worktree: ../khealth-spec-wellness-reminders
Branch: spec/wellness-reminders
Design folder: docs/designs/wellness-reminders/

No sandbox needed for spec work.
```

### Scenario 3: Impl worktree (with sandbox)

```
$ kinfra impl wellness-reminders/M1

Found milestone: docs/designs/wellness-reminders/implementation/M1_foundation.md
Created worktree: ../khealth-impl-wellness-reminders-M1
Branch: impl/wellness-reminders-M1

Claiming sandbox slot 1 (ports: api=8081)
Starting services... done (12s)
Health check: GET http://localhost:8081/api/v1/health OK

Sandbox ready:
  API:        http://localhost:8081
  Jaeger UI:  http://localhost:46686 (shared)
  Grafana:    http://localhost:43000 (shared)
```

### Scenario 4: With agent-deck (optional)

```
$ kinfra impl wellness-reminders/M1 --session

[... same as above, plus:]

agent-deck session added: wellness-reminders/M1
Starting Claude... done
Sending: /kmilestone wellness-reminders/M1

Switch to agent-deck TUI to monitor progress.
```

### Scenario 5: Cleanup

```
$ kinfra done wellness-reminders-M1

Stopping sandbox (slot 1)... done
Releasing slot 1... done
Removing worktree... done
```

### Scenario 6: Worktree-only project (no Docker)

For projects with no `infra.toml` or no compose file, `kinfra spec` and `kinfra impl` both work — they just create worktrees and skip the sandbox step. Implementation worktrees still get branch isolation and the cleanup workflow.

### Scenario 7: Multiple projects running simultaneously

```
$ kinfra worktrees

PROJECT   WORKTREE                              TYPE   SLOT   API PORT   STATUS
khealth   khealth-impl-wellness-reminders-M1    impl   1      8081       running
khealth   khealth-spec-notifications            spec   -      -          -
ktrdr     (managed by ktrdr's own kinfra)       -      -      -          -
```

Shared observability:
  Jaeger:     http://localhost:46686  (all projects)
  Grafana:    http://localhost:43000  (all projects)

## Key Decisions

### Decision 1: Python CLI installed via uv

**Choice:** Python CLI using Typer, installed as part of devops-ai via `uv tool install -e .`

**Alternatives considered:** Shell script (too fragile for registry/port management), pure skill-based (non-deterministic for infrastructure operations)

**Rationale:** Port allocation, JSON registry, health polling, and compose override generation need proper data structures and error handling. Python with Typer is proven (ktrdr's kinfra). `uv tool install -e .` means `git pull` updates the CLI — same developer experience as the symlink model for skills.

### Decision 2: Project adapter as .devops-ai/infra.toml

**Choice:** Structured TOML file, separate from `project.md`

**Alternatives considered:** Extending project.md (fragile to parse deterministically), YAML (less Pythonic), project-side code/scripts (too much friction)

**Rationale:** The CLI needs deterministic parsing — it can't rely on an LLM to read markdown. TOML is the Python ecosystem standard (`pyproject.toml`). Keeping it separate from `project.md` means skills keep reading markdown, CLI reads TOML — each tool uses the format it's best at. The file is small (~10-25 lines) and generated by `kinfra init`.

### Decision 3: Port isolation via global slot offset

**Choice:** Each port gets `base + slot_id`. Slot IDs are global across all projects (1-100). TCP bind test as runtime safety net.

**Alternatives considered:** Random ports (hard to remember), per-project slot numbering (cross-project port conflicts invisible), port ranges per project (over-engineered)

**Rationale:** Simple, deterministic, proven in ktrdr. Global numbering means if khealth claims slot 1 and another project claims slot 2, no ports can ever collide. TCP bind test at claim time catches edge cases where different base ports from different projects produce the same offset port (e.g., project A base=8080 slot 3 = 8083 vs project B base=8081 slot 2 = 8083).

### Decision 4: Slot cap of 100

**Choice:** Maximum 100 slots (slot IDs 1-100).

**Rationale:** Port offsets stay within valid range (max base port ~65400 + 100 = 65500 < 65535). 100 concurrent sandboxes across all projects is more than enough for any development machine.

### Decision 5: Agent-deck integration is optional

**Choice:** `kinfra` checks if `agent-deck` is on PATH. If available, `--session` flag triggers session management. If not installed, silently skips with a note.

**Alternatives considered:** Required dependency (limits adoption), separate skill only (duplicates orchestration logic)

**Rationale:** agent-deck is extremely useful but not widely available. The core value — isolated worktrees + sandboxes — works without it. Users who have it get the bonus of session management.

### Decision 6: On-demand slot directories

**Choice:** `kinfra impl` creates `~/.devops-ai/slots/<project>-<N>/` on the fly when claiming a slot. No pre-provisioning needed.

**Alternatives considered:** Pre-provisioned slot directories (ktrdr model — useful when startup is slow, but adds setup complexity)

**Rationale:** Simple projects start in seconds — no need to pre-create infrastructure. The slot directory holds `.env.sandbox` and `docker-compose.override.yml`. Created on claim, cleaned up on release. Pre-provisioning can be added later as an optimization for projects with slow startup.

### Decision 7: Compose parameterization by kinfra init

**Choice:** `kinfra init` updates the project's docker-compose.yml to use environment variables for host ports (e.g., `${KHEALTH_API_PORT:-8080}:8080`) and adds comments explaining the pattern for coding agents.

**Alternatives considered:** Separate compose file for sandboxes (duplication), runtime compose manipulation (fragile)

**Rationale:** The compose file remains fully functional without kinfra (defaults kick in). With kinfra, `.env.sandbox` overrides the host ports. The comments teach coding agents how the parameterization works, preventing them from accidentally hardcoding ports.

### Decision 8: Shared observability stack

**Choice:** One always-running Jaeger + Grafana + Prometheus instance on dedicated devops-ai ports, serving all sandboxes. Projects don't run their own observability services. OTEL resource attributes (`service.namespace`) provide per-project/slot namespacing.

**Alternatives considered:** Per-sandbox observability (current ktrdr model — works but causes port explosion and resource waste)

**Rationale:** Every project uses OTEL with the same pattern (OTLP gRPC to Jaeger). Running separate instances per sandbox wastes ports and RAM for identical infrastructure. A shared stack eliminates 3+ ports per sandbox and provides a single place to view all traces/metrics.

### Decision 9: ktrdr coexistence

**Choice:** ktrdr's existing sandboxes, local-prod, and observability are completely untouched. The shared devops-ai observability stack uses a dedicated port range that does not conflict with ktrdr's ports (standard or offset). ktrdr migrates when ready, on its own terms.

**Alternatives considered:** Force ktrdr migration (disruptive), share ktrdr's Jaeger (too tightly coupled)

**Rationale:** ktrdr's local-prod uses standard ports (16686 for Jaeger, 3000 for Grafana, 9090 for Prometheus). ktrdr's sandbox slots offset from those. The shared devops-ai stack uses a separate range (e.g., 4xxxx) to guarantee zero conflicts. This means both systems can run simultaneously without interference.

### Decision 10: Slot directory pattern (from ktrdr)

**Choice:** Infrastructure state lives in `~/.devops-ai/slots/<project>-<N>/`, not in the worktree. Docker compose runs from the slot directory, referencing the worktree's compose file.

**Alternatives considered:** Override and env files in worktree (mixes code and infrastructure)

**Rationale:** Proven in ktrdr. Worktrees stay pure code. Slot directories are easy to find for cleanup. Compose file comes from the worktree so feature-branch compose changes are reflected in the sandbox.

### Decision 11: Projects own their port declarations

**Choice:** Projects declare all ports they need in `infra.toml`. kinfra offsets them all. No assumptions about which ports are "necessary."

**Rationale:** Different projects have different needs. ktrdr publishes worker ports for CLI access and debugging. khealth might only need one API port. kinfra doesn't opine — it just offsets whatever's declared.

### Decision 12: Installation model

**Choice:** `install.sh` updated to also run `uv tool install -e .` for the CLI, alongside existing symlinks for skills.

**Alternatives considered:** Separate install step (forgettable), containerized CLI (overkill)

**Rationale:** One install command. Editable install means `git pull` in devops-ai updates both skills (via symlinks) and CLI (via editable package). Same developer experience.

## Open Questions

1. **Shared observability port range** — Need to pick specific ports for the shared Jaeger/Grafana/Prometheus that avoid ktrdr's range (standard + offsets up to ~+10). Current thinking: 4xxxx range (e.g., Jaeger UI 46686, OTLP 44317, Grafana 43000, Prometheus 49090). Final numbers to be decided during implementation.

2. **Compose file generation** — If a project has no docker-compose.yml at all, should `kinfra init` help create one? Or is that out of scope (project must bring its own compose file to use sandboxes)?

3. **Coding agent skill** — Should there be a devops-ai skill that teaches coding agents how kinfra-managed compose files work (the env var parameterization pattern, what not to hardcode)? Useful but can be deferred.

4. **ktrdr migration path** — When ktrdr is ready to migrate, the steps would be: (a) create infra.toml, (b) update compose to use devops-ai's shared observability, (c) switch from ktrdr's kinfra to devops-ai's kinfra. Details to be designed when needed.
