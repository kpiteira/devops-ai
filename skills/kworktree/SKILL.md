---
name: kworktree
description: Worktree and sandbox management via kinfra CLI commands.
metadata:
  version: "0.1.0"
---

# kworktree — Worktree & Sandbox Management

Use this skill when the user asks to create, manage, or clean up development worktrees and sandboxes via `kinfra`.

---

## Context Detection

Before running kinfra commands, determine where you are:

```bash
# Check if in a worktree
git worktree list
# Branch pattern: spec/<feature> or impl/<feature>-<milestone>

# Check sandbox status
kinfra status
# Shows: slot ID, ports, project name (if in a sandbox worktree)
```

---

## Commands Reference

### `kinfra init`

Initialize kinfra for the current project. Run once per project.

```bash
kinfra init
# Interactive: detects compose file, services, ports
# Generates: .devops-ai/infra.toml
# Updates: docker-compose.yml (parameterizes host ports with env vars)
```

### `kinfra spec <feature>`

Create a design worktree (no sandbox).

```bash
kinfra spec wellness-reminders
# Creates: ../<prefix>-spec-wellness-reminders/
# Branch: spec/wellness-reminders
# Design dir: docs/designs/wellness-reminders/
```

### `kinfra impl <feature>/<milestone> [--no-session]`

Create an implementation worktree with sandbox. Automatically creates an agent-deck session and launches Claude with `/kbuild`.

```bash
kinfra impl wellness-reminders/M1
# Creates worktree + claims slot + starts Docker sandbox
# Starts agent-deck session + launches Claude with /kbuild
# Output includes: slot ID, port mappings

kinfra impl wellness-reminders/M1 --no-session
# Same as above but skips agent-deck session
```

### `kinfra done <name> [--force]`

Remove a worktree and clean up its sandbox.

```bash
kinfra done wellness-reminders-M1
# Stops sandbox, releases slot, removes worktree
# Fails if uncommitted changes (use --force to override)

kinfra done wellness-reminders-M1 --force
# Removes even with dirty state
```

### `kinfra worktrees`

List all active worktrees across the project.

```bash
kinfra worktrees
# Shows: worktree name, type (spec/impl), slot, ports, status
```

### `kinfra status`

Show sandbox details for the current directory.

```bash
kinfra status
# Shows: project, slot ID, status, ports
```

### `kinfra observability up|down|status`

Manage the shared observability stack.

```bash
kinfra observability up      # Start Jaeger + Grafana + Prometheus
kinfra observability down    # Stop the stack
kinfra observability status  # Show service health and endpoints
```

---

## Workflows

**Design (spec):** `kinfra spec <feature>` → work → `kinfra done <feature>`

**Implementation (impl):** `kinfra impl <feature>/<milestone>` → sandbox + Claude session with `/kbuild` → `kinfra done <feature>-<milestone>`

**Without agent-deck:** `kinfra impl <feature>/<milestone> --no-session` → sandbox only, no Claude session

---

## Sandbox-Aware Coding

When writing code that connects to services, use dynamic ports from `kinfra status` or environment variables from `.devops-ai/infra.toml`. Do NOT hardcode base ports.

```python
# WRONG — hardcoded port
url = "http://localhost:8080/api/v1/health"

# RIGHT — use the sandbox port from kinfra status
# Check: kinfra status → API_PORT: 8081
url = "http://localhost:8081/api/v1/health"
```

Port formula: `actual_port = base_port + slot_id`. The `.env.sandbox` file in the slot directory contains all port mappings as environment variables.

For OTEL configuration in sandbox services:
- Exporter endpoint: `http://devops-ai-jaeger:4317` (container network)
- Resource attributes: `service.namespace=<project>-slot-<N>`

---

## Observability

The shared observability stack serves all sandboxes:

| Service    | URL                        | Purpose            |
|------------|----------------------------|--------------------|
| Jaeger UI  | http://localhost:46686     | Distributed traces |
| Grafana    | http://localhost:43000     | Dashboards         |
| Prometheus | http://localhost:49090     | Metrics            |
| OTLP gRPC  | http://localhost:44317     | Trace ingestion    |

Filter traces by namespace in Jaeger UI:
- Service name format: `<project>-slot-<N>/<service>`
- Example: `khealth-slot-1/wellness-agent`

---

## Error Handling

| Situation | What to do |
|-----------|------------|
| `kinfra init` not run | Run `kinfra init` first — generates infra.toml |
| Sandbox fails to start | Check `docker compose logs` in the slot directory |
| Health check timeout | Services may still be starting — check logs |
| Dirty worktree on done | Commit or stash changes, or use `--force` |
| Port conflict | kinfra auto-selects next available slot |
| agent-deck not installed | Session skipped with warning, impl still works |

---

## Project Configuration

kinfra reads `.devops-ai/infra.toml` for project-specific settings (ports, compose file, health endpoint). All port values are base ports — kinfra offsets them by slot ID for isolation. Run `kinfra init` to generate this file.
