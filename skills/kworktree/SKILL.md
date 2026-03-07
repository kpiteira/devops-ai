---
name: kworktree
description: Worktree and sandbox management via kinfra CLI commands.
metadata:
  version: "0.2.0"
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

### `kinfra sandbox start`

Restart sandbox for an existing worktree (re-provisions secrets and files).

### `kinfra sandbox rebuild`

Rebuild sandbox with latest code changes. Re-provisions secrets/files AND rebuilds Docker images from source. **Use this after code changes** — `start` only restarts existing images.

### `kinfra observability up|down|status`

Manage the shared observability stack.

---

## Workflows

### Implementation (the main workflow)

Every `kinfra impl` MUST produce three things: worktree + sandbox + agent-deck child session.

**Step 1: Create worktree**
```bash
kinfra impl <feature>/<milestone> --no-session
```

**Step 2: Create agent-deck child session (MANDATORY)**

This is NOT optional. After every `kinfra impl`, immediately create the session:

```bash
# Get current session name
agent-deck session current

# Create child session (substitute actual values)
agent-deck add -t "<feature>/<milestone>" -c claude --parent <current-session-name> <worktree-path>

# Example:
agent-deck add -t "health-advisor/M2" -c claude --parent khealth /Users/karl/Documents/dev/wellness-agent-impl-health-advisor-M2
```

The `--parent` flag links the child to the current session — this is how agent-deck tracks which sessions spawned which.

**Step 3: Report to user**
Tell the user the session is ready and how to start it:
```
agent-deck session start <feature>/<milestone>
```

### Design (spec)

`kinfra spec <feature>` → work → `kinfra done <feature>`

### Cleanup

`kinfra done <feature>-<milestone>` — also removes the agent-deck session automatically.

---

## Sandbox Operations

### After code changes: rebuild

Source code is COPY'd into Docker images at build time. There is NO hot reload. After changing code, you MUST rebuild:

```bash
# From the worktree directory:
kinfra sandbox rebuild
# Re-provisions secrets/files, then runs docker compose up --build -d
```

Do NOT run raw `docker compose` commands. `kinfra sandbox rebuild` handles compose files, override files, env files, and secrets correctly.

### Restarting without rebuild

```bash
kinfra sandbox start
# Re-provisions secrets/files, restarts containers with existing images
```

### Discovering the sandbox

Before any E2E or sandbox interaction, always discover the sandbox state:

```bash
kinfra status
# Shows: slot ID, ports, whether sandbox is running
```

Port formula: `actual_port = base_port + slot_id`. The `.env.sandbox` file in the slot directory contains all port mappings as environment variables.

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
| Port conflict | `kinfra done` the old worktree first, or kinfra auto-selects next slot |
| Orphaned containers after done | `docker ps` to find them, `docker rm -f` to clean up |
| Code changes not reflected | Run `kinfra sandbox rebuild` (not `start`) |

---

## Project Configuration

kinfra reads `.devops-ai/infra.toml` for project-specific settings (ports, compose file, health endpoint). All port values are base ports — kinfra offsets them by slot ID for isolation. Run `kinfra init` to generate this file.
