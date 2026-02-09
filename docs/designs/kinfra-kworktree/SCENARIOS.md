# Design Validation: kinfra + kworktree

**Date:** 2026-02-08
**Documents Validated:**
- Design: DESIGN.md
- Architecture: ARCHITECTURE.md
- Scope: Full design (all components)

## Validation Summary

**Scenarios Validated:** 13 (all traced)
**Critical Gaps Found:** 5 (all resolved)
**Important Gaps:** 5 (resolutions recommended)
**Minor Gaps:** 9 (noted for implementation)
**Interface Contracts:** Defined for infra.toml schema, registry schema, slot directory, .env.sandbox, override YAML, CLI state transitions, Docker compose invocations

## Key Decisions Made

These decisions came from the validation conversation and should inform implementation:

1. **Code mount paths use Docker-style syntax** — `code = ["src/:/app/src", "tests/:/app/tests"]`
   - Context: GAP-3 — override generator needs both host and container paths
   - Trade-off: Slightly more verbose config, but familiar syntax and unambiguous

2. **Compose file copied to slot dir for teardown safety** — `up` uses worktree's version, `down` uses slot dir's copy
   - Context: GAP-15 — if worktree is manually deleted, `docker compose down` needs a compose file
   - Trade-off: Slight staleness risk on `down` (old copy), but Docker compose down is resilient to minor differences

3. **Impl without infra.toml creates worktree without sandbox** — no error, just no Docker
   - Context: GAP-13 — making `impl` useful for pure-code projects too
   - Trade-off: None — strictly more capable. Prefix falls back to directory name or project.md name

4. **All Docker compose paths are absolute** — no ambiguity about working directory
   - Context: GAP-8 — compose runs from slot dir but references worktree compose file
   - Trade-off: Longer command lines, but zero ambiguity

5. **Start simple with Docker network handling** — assume default network, detect custom networks during init
   - Context: GAP-18 — Docker compose override `networks:` replaces rather than merges
   - Trade-off: Projects with custom networks need manual attention. Can add `[sandbox.networks]` later

## Resolved Gaps (Full Detail)

### Critical Gaps

**GAP-3: Code mount host→container path mapping**
- **Category:** Data Shape
- **Resolution:** Docker-style syntax in infra.toml: `code = ["src/:/app/src", "tests/:/app/tests"]`. Default (no colon) assumes `/app/<dirname>`.

**GAP-8: Docker compose working directory**
- **Category:** Integration
- **Resolution:** Always use absolute paths for `-f` flags. Store absolute paths in registry.

**GAP-13: Impl without infra.toml**
- **Category:** State Machine
- **Resolution:** `impl` without infra.toml creates worktree without sandbox. Prefix falls back to directory name or project.md name. No error.

**GAP-15: Orphan container cleanup**
- **Category:** State Machine / Infrastructure
- **Resolution:** Copy compose file into slot dir at claim time. `up` uses worktree's version (latest code). `down` uses slot dir's copy (teardown safety). Slot dir contents: `.env.sandbox`, `docker-compose.yml` (copy), `docker-compose.override.yml` (generated).

**GAP-18: Docker compose network override**
- **Category:** Integration
- **Resolution:** Start with assumption of default network. Detect custom networks during `kinfra init` and warn. Add optional `[sandbox.networks]` section to infra.toml if needed.

### Important Gaps

**GAP-4: YAML rewriting strategy**
- **Category:** Implementation
- **Resolution:** Use `ruamel.yaml` (round-trip mode) for compose file modification. Preserves comments and ordering. Add as dependency.

**GAP-11: Partial docker compose up cleanup**
- **Category:** Error Handling
- **Resolution:** After `docker compose up -d` fails, always run `docker compose down` to clean partially-started containers before releasing slot.

**GAP-14: Stale registry cleanup trigger**
- **Category:** State Machine
- **Resolution:** Run stale check on `kinfra worktrees`, `kinfra status`, and `kinfra impl` (before slot allocation). Check: does worktree_path exist? Does slot_dir exist? If either missing, entry is stale — clean up registry entry. Also attempt to stop orphaned containers via slot dir's compose copy.

**GAP-16: kinfra init on already-initialized project**
- **Category:** State Machine
- **Resolution:** Detect existing infra.toml, show current config, ask "Update existing configuration? (y/N)". If yes, run interactive flow with current values as defaults. Never silently overwrite.

**GAP-19: Project-specific OTEL env var names**
- **Category:** Integration
- **Resolution:** Add optional `[sandbox.otel]` section to infra.toml with `endpoint_var` field. Default to standard `OTEL_EXPORTER_OTLP_ENDPOINT`. Override generator uses configured var name.

### Minor Gaps

**GAP-1:** Name vs prefix — ask as two separate questions in init. Default prefix = directory name.

**GAP-2:** First-run bootstrap — create `~/.devops-ai/` directory tree lazily on first use of any command.

**GAP-5:** Docker not running — detect early in init with `docker info`. Error: "Docker is not running."

**GAP-6:** `kinfra done` cross-project search — search global registry first, fall back to `git worktree list`. Registry is primary lookup.

**GAP-9:** Container stop before worktree removal — critical ordering constraint. Already correct in architecture. Mark in code.

**GAP-10:** `kinfra worktrees` scope — list from global registry (all projects), not just current project.

**GAP-12:** Log why slots are skipped — "Slot 1 skipped: port 8001 in use by another process."

**GAP-17:** Done with missing slot dir — check slot_dir exists before docker compose down. If missing, skip with warning. Still release registry and remove worktree.

**GAP-20:** Agent-deck send timing — add configurable delay (default 3s) between session start and session send, or poll for readiness.

**GAP-21:** Agent-deck active session — warn if session state is "running" during done. Suggest `--force`.

## Interface Contracts

### infra.toml Schema

```toml
# === Required ===

[project]
name = "khealth"                    # project name
prefix = "khealth"                  # worktree prefix (optional, defaults to name)

# === Optional: Sandbox Configuration ===
# Omit entire [sandbox] section for worktree-only projects

[sandbox]
compose_file = "docker-compose.yml" # path relative to project root

[sandbox.health]
endpoint = "/api/v1/health"         # HTTP GET path
port_var = "KHEALTH_API_PORT"       # which port env var to use for health check
timeout = 60                        # seconds (optional, default 60)

[sandbox.ports]                     # env_var = base_port
KHEALTH_API_PORT = 8080

[sandbox.mounts]                    # Docker-style host:container[:ro]
code = ["src/:/app/src", "tests/:/app/tests"]
code_targets = ["wellness-agent"]   # compose services receiving code mounts
shared = []                         # dirs from main repo (optional)
shared_targets = []                 # compose services receiving shared mounts (optional)

[sandbox.otel]                      # optional
endpoint_var = "OTEL_EXPORTER_OTLP_ENDPOINT"  # default
namespace_var = "OTEL_RESOURCE_ATTRIBUTES"      # default

[sandbox.networks]                  # optional
include = []                        # custom networks to preserve in override
```

### Registry Schema (v1)

```json
{
  "version": 1,
  "slots": {
    "1": {
      "slot_id": 1,
      "project": "khealth",
      "worktree_path": "/abs/path/to/khealth-impl-wellness-reminders-M1",
      "slot_dir": "/abs/path/to/.devops-ai/slots/khealth-1",
      "compose_file_copy": "/abs/path/to/.devops-ai/slots/khealth-1/docker-compose.yml",
      "ports": {
        "KHEALTH_API_PORT": 8081
      },
      "claimed_at": "2026-02-08T15:30:00Z",
      "status": "running"
    }
  }
}
```

### Slot Directory Contents

```
~/.devops-ai/slots/<project>-<slot_id>/
  .env.sandbox                    # COMPOSE_PROJECT_NAME + port vars
  docker-compose.yml              # copied from worktree at claim time
  docker-compose.override.yml     # generated: mounts + observability + OTEL
```

### .env.sandbox Format

```env
COMPOSE_PROJECT_NAME=khealth-slot-1
KHEALTH_API_PORT=8081
```

### docker-compose.override.yml Format

```yaml
# Generated by kinfra impl — do not edit manually
# Worktree: /abs/path/to/khealth-impl-wellness-reminders-M1
# Slot: khealth-1
# Generated at: 2026-02-08T15:30:00Z

networks:
  devops-ai-observability:
    external: true

services:
  wellness-agent:
    networks:
      - default
      - devops-ai-observability
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://devops-ai-jaeger:4317
      - OTEL_RESOURCE_ATTRIBUTES=service.namespace=khealth-slot-1
    volumes:
      - /abs/path/to/worktree/src:/app/src
      - /abs/path/to/worktree/tests:/app/tests
```

### CLI State Transitions

```
No worktree
  │
  ├─[kinfra spec <feature>]──→ Spec Worktree
  │                                │
  │                                ├─[kinfra done <name>]──→ No worktree (if clean)
  │                                ├─[kinfra done <name>]──→ BLOCKED (if dirty)
  │                                └─[kinfra done --force]──→ No worktree
  │
  ├─[kinfra impl <f/M>, has infra.toml + sandbox]──→ Impl Worktree + Sandbox Running
  │                                                      │
  │                                                      ├─[kinfra done]──→ No worktree (if clean)
  │                                                      │                  containers stopped
  │                                                      │                  slot released
  │                                                      ├─[kinfra done]──→ BLOCKED (if dirty)
  │                                                      └─[kinfra done --force]──→ No worktree
  │
  └─[kinfra impl <f/M>, no infra.toml or no sandbox section]──→ Impl Worktree (no sandbox)
                                                                    │
                                                                    ├─[kinfra done]──→ No worktree
                                                                    └─[kinfra done --force]──→ No worktree
```

### Docker Compose Invocation Contracts

**Start sandbox (uses worktree's compose for latest code):**
```bash
docker compose \
  -f /abs/worktree/docker-compose.yml \
  -f /abs/slot_dir/docker-compose.override.yml \
  --env-file /abs/slot_dir/.env.sandbox \
  up -d
```

**Stop sandbox (uses slot dir's compose copy for teardown safety):**
```bash
docker compose \
  -f /abs/slot_dir/docker-compose.yml \
  -f /abs/slot_dir/docker-compose.override.yml \
  --env-file /abs/slot_dir/.env.sandbox \
  down
```

**Partial failure cleanup (after failed up):**
```bash
docker compose \
  -f /abs/slot_dir/docker-compose.yml \
  -f /abs/slot_dir/docker-compose.override.yml \
  --env-file /abs/slot_dir/.env.sandbox \
  down
```

## Recommended Milestone Structure

### Milestone 1: Foundation — CLI skeleton + config + worktrees

**User Story:** As a developer, I can run `kinfra init` to generate config, then `kinfra spec` and `kinfra done` to manage worktrees.

**Scope:**
- pyproject.toml + package structure + uv tool install
- Config Loader: parse infra.toml, find_project_root, validate
- Worktree Manager: create_spec, remove, check_dirty, list
- CLI: init (interactive prompts → infra.toml + compose parameterization)
- CLI: spec (create spec worktree)
- CLI: done (remove worktree with dirty check)
- CLI: worktrees (list from git worktree list)
- install.sh updated with uv tool install step

**E2E Test:**
```
Given: A project with docker-compose.yml
When:  kinfra init (answer prompts)
Then:  .devops-ai/infra.toml exists, compose file parameterized

Given: Initialized project
When:  kinfra spec my-feature
Then:  ../prefix-spec-my-feature/ exists, branch spec/my-feature created

When:  kinfra done my-feature
Then:  Worktree removed, branch cleaned up
```

**Depends On:** Nothing

---

### Milestone 2: Sandbox slots — registry + ports + sandbox lifecycle

**User Story:** As a developer, I can run `kinfra impl feature/M1` and get a worktree with a running sandbox on isolated ports, then clean up with `kinfra done`.

**Scope:**
- Slot Registry: load, save, allocate, claim, release, stale cleanup
- Port Allocator: compute_ports, TCP bind test
- Sandbox Manager: slot dirs, env file, override generation, start/stop, health gate
- Compose file copy to slot dir (teardown safety)
- CLI: impl (worktree + slot + sandbox)
- CLI: done extended (stop + release + remove)
- CLI: status (current sandbox details)
- Partial failure handling (compose down on failed up)

**E2E Test:**
```
Given: Initialized project with compose file and milestone file
When:  kinfra impl feature/M1
Then:  Worktree created, slot claimed in registry, containers running, health OK

When:  kinfra status
Then:  Shows slot number, ports, container status

When:  kinfra done feature-M1
Then:  Containers stopped, slot released, slot dir removed, worktree removed
```

**Depends On:** Milestone 1

---

### Milestone 3: Shared observability

**User Story:** As a developer, sandbox traces appear in a shared Jaeger instance without per-project observability setup.

**Scope:**
- Observability Manager: start, stop, status, ensure_running
- Observability compose template (Jaeger + Grafana + Prometheus on devops-ai ports)
- Docker network: devops-ai-observability
- Override generator updated: add network + OTEL env vars
- CLI: observability up/down/status
- Auto-start from kinfra impl
- OTEL namespace (service.namespace per project/slot)

**E2E Test:**
```
Given: Shared observability stack running
When:  kinfra impl feature/M1 (sandbox started)
Then:  Sandbox containers connected to devops-ai-observability network
       OTEL env vars set pointing to shared Jaeger
       Traces visible in Jaeger UI filtered by service.namespace
```

**Depends On:** Milestone 2

---

### Milestone 4: Agent-deck integration + kworktree skill

**User Story:** As a developer, `kinfra impl feature/M1 --session` creates an agent-deck session with Claude running and the milestone command auto-sent.

**Scope:**
- Agent-Deck module: is_available, add/remove/start/send session
- --session flag on impl and cleanup in done
- Graceful degradation (agent-deck not installed)
- kworktree skill (SKILL.md) for conversational use in AI tools
- Send timing (delay or readiness poll)

**E2E Test:**
```
Given: agent-deck installed, initialized project
When:  kinfra impl feature/M1 --session
Then:  Agent-deck session visible, Claude running, milestone command sent

When:  kinfra done feature-M1
Then:  Session removed, sandbox stopped, worktree removed
```

**Depends On:** Milestone 2 (not M3 — agent-deck works without shared observability)
