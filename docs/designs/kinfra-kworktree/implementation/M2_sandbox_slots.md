---
design: docs/designs/kinfra-kworktree/DESIGN.md
architecture: docs/designs/kinfra-kworktree/ARCHITECTURE.md
---

# Milestone 2: Sandbox Slots — registry + ports + sandbox lifecycle

**Goal:** A developer can run `kinfra impl feature/M1` and get a worktree with a running sandbox on isolated ports, then clean up with `kinfra done`.

**Branch:** `impl/kinfra-kworktree-M2`
**Builds on:** Milestone 1

---

## Task 2.1: Port Allocator

**File(s):**
- `src/devops_ai/ports.py` (create)
- `tests/unit/test_ports.py` (create)

**Type:** CODING
**Task Categories:** Configuration

**Description:**
Implement port offset computation and conflict detection. Each port is `base_port + slot_id`. TCP bind test probes each port before claiming to catch conflicts with non-kinfra processes (including ktrdr's own sandboxes).

**Implementation Notes:**
- `compute_ports(config, slot_id)` → `dict[str, int]` mapping env_var to actual_port
- `check_ports_available(ports)` → `list[PortConflict]` — attempt TCP `bind()` on each port, release immediately
  - Use `socket.socket(AF_INET, SOCK_STREAM)` with `SO_REUSEADDR`
  - Bind to `("127.0.0.1", port)` — if bind fails, port is in use
  - Return list of conflicts with port number and error message
- `check_base_port_safety(config, registry)` → `list[str]` — warnings if base ports from this project are within 100 of another project's base ports (advisory, not blocking)
- Port formula: `actual_port = base_port + slot_id`
- Slot IDs: 1-100 (slot 0 is reserved/unused)

**Tests:**
- Unit: `tests/unit/test_ports.py`
  - `test_compute_ports_simple`: slot 1 + base 8080 → 8081
  - `test_compute_ports_multiple`: multiple ports all offset correctly
  - `test_compute_ports_slot_100`: max slot, ports still valid (< 65535)
  - `test_check_ports_available_all_free`: returns empty list
  - `test_check_ports_available_conflict`: bind a port, verify detected
  - `test_base_port_safety_warning`: two projects with base ports 1 apart → warning
  - `test_base_port_safety_ok`: two projects with base ports 1000 apart → no warning

**Acceptance Criteria:**
- [ ] Port offset formula correct for all slot IDs 1-100
- [ ] TCP bind test detects ports already in use
- [ ] Base port safety check warns about proximity

---

## Task 2.2: Slot Registry

**File(s):**
- `src/devops_ai/registry.py` (create)
- `tests/unit/test_registry.py` (create)

**Type:** CODING
**Task Categories:** Persistence, State Machine

**Description:**
Implement the global slot registry that tracks all claimed slots across all projects. Persists to `~/.devops-ai/registry.json`. Handles allocation (find next free), claim, release, and stale entry cleanup.

**Implementation Notes:**
- `Registry` dataclass: `version: int`, `slots: dict[int, SlotInfo]`
- `SlotInfo` dataclass: `slot_id`, `project`, `worktree_path`, `slot_dir`, `compose_file_copy` (abs path), `ports` (dict), `claimed_at` (ISO), `status` ("running"|"stopped")
- `load_registry()`: read JSON, create file/dir if doesn't exist, handle empty/corrupt file
- `save_registry()`: write JSON with indent for readability
- `allocate_slot(registry, config)`: iterate 1-100, skip claimed, compute ports, TCP bind test, return first available
  - Log skip reasons: "Slot N skipped: port XXXX in use"
- `claim_slot()`: add SlotInfo to registry, save
- `release_slot()`: remove slot entry, save
- `get_slot_for_worktree(registry, path)`: lookup by worktree_path
- `clean_stale_entries(registry)`: for each slot, check worktree_path and slot_dir exist; if either missing, remove entry and log warning
- File locking: use `fcntl.flock()` on the registry file during write to prevent concurrent corruption (multiple terminals running kinfra simultaneously)

**Tests:**
- Unit: `tests/unit/test_registry.py`
  - `test_load_empty_registry`: no file → empty registry
  - `test_load_existing_registry`: valid JSON → correct Registry
  - `test_save_and_reload`: round-trip persistence
  - `test_claim_and_release`: claim adds, release removes
  - `test_allocate_skips_claimed`: slot 1 claimed → allocates slot 2
  - `test_allocate_skips_port_conflict`: mock port in use → skips slot
  - `test_allocate_exhausted`: all 100 claimed → error
  - `test_get_slot_for_worktree`: lookup by path
  - `test_clean_stale_missing_worktree`: worktree path doesn't exist → cleaned
  - `test_clean_stale_missing_slot_dir`: slot dir doesn't exist → cleaned
  - `test_clean_stale_both_exist`: valid entry preserved

**Acceptance Criteria:**
- [ ] Registry persists to JSON and reloads correctly
- [ ] Slot allocation finds next free slot with TCP bind test
- [ ] Stale entries cleaned when worktree/slot dir missing
- [ ] File locking prevents concurrent corruption
- [ ] All slots 1-100 tracked correctly

---

## Task 2.3: Sandbox Manager — file generation

**File(s):**
- `src/devops_ai/sandbox.py` (create)
- `tests/unit/test_sandbox.py` (create)

**Type:** CODING
**Task Categories:** Cross-Component, Configuration

**Description:**
Implement slot directory creation, .env.sandbox generation, and docker-compose.override.yml generation. The override mounts worktree code into containers and joins the observability network (network integration completed in M3, but the override structure is set up here with a conditional check).

**Implementation Notes:**
- `create_slot_dir(project, slot_id)` → creates `~/.devops-ai/slots/<project>-<slot_id>/`, returns Path
- `remove_slot_dir(slot_dir)` → `shutil.rmtree()`
- `copy_compose_to_slot(compose_path, slot_dir)` → copies worktree's compose file for teardown safety
- `generate_env_file(config, slot)` → writes `.env.sandbox`:
  ```
  COMPOSE_PROJECT_NAME=<project>-slot-<slot_id>
  <ENV_VAR_1>=<base_port_1 + slot_id>
  <ENV_VAR_2>=<base_port_2 + slot_id>
  ```
- `generate_override(config, slot, worktree_path, main_repo_path)` → writes `docker-compose.override.yml`:
  - Parse Docker-style mount syntax: `"src/:/app/src"` → `<worktree>/src:/app/src`
  - For shared mounts: `<main_repo>/data:/app/data`
  - All paths are absolute
  - Add header comment with worktree path, slot name, timestamp
  - Observability network section: include only if `devops-ai-observability` Docker network exists (check with `docker network inspect`). If not present, skip (M3 adds it).
  - OTEL env vars: include only if observability network is present

**Tests:**
- Unit: `tests/unit/test_sandbox.py`
  - `test_create_slot_dir`: directory created at expected path
  - `test_env_file_content`: correct COMPOSE_PROJECT_NAME and port vars
  - `test_env_file_port_offset`: ports correctly offset by slot_id
  - `test_override_code_mounts`: volumes section has absolute worktree paths
  - `test_override_shared_mounts`: volumes section has absolute main_repo paths
  - `test_override_readonly_mount`: `:ro` preserved in override
  - `test_override_header_comment`: header has worktree path and timestamp
  - `test_override_multiple_targets`: multiple services each get their mounts
  - `test_copy_compose`: compose file copied to slot dir

**Acceptance Criteria:**
- [ ] Slot directory created at `~/.devops-ai/slots/<project>-<N>/`
- [ ] .env.sandbox has correct COMPOSE_PROJECT_NAME and offset ports
- [ ] Override YAML has correct absolute-path volume mounts
- [ ] Docker-style mount syntax parsed correctly (including :ro)
- [ ] Compose file copied to slot dir for teardown safety
- [ ] Override gracefully handles missing observability network (M3 adds it)

---

## Task 2.4: Sandbox Manager — Docker lifecycle + health gate

**File(s):**
- `src/devops_ai/sandbox.py` (modify)
- `tests/unit/test_sandbox_lifecycle.py` (create)

**Type:** CODING
**Task Categories:** External, Background/Async

**Description:**
Implement Docker compose start/stop and health gate polling. Start uses the worktree's compose file (latest code). Stop uses the slot dir's compose copy (teardown safety). Health gate polls an HTTP endpoint with configurable timeout.

**Implementation Notes:**
- `start_sandbox(config, slot, worktree_path)`:
  - Run: `docker compose -f <worktree>/compose -f <slot>/override --env-file <slot>/.env.sandbox up -d`
  - All paths absolute
  - Capture stdout/stderr
  - On failure: run `docker compose down` (same args) to clean partial containers, then raise
- `stop_sandbox(slot)`:
  - Run: `docker compose -f <slot>/compose_copy -f <slot>/override --env-file <slot>/.env.sandbox down`
  - Uses slot dir's compose copy (not worktree — worktree might be gone)
  - Ignore errors (best-effort cleanup)
- `run_health_gate(config, slot)` → bool:
  - Compute health URL: `http://localhost:<offset_port>/<endpoint>`
  - Poll every 2 seconds
  - Timeout from config (default 60s)
  - Return True on HTTP 200, False on timeout
  - Use `urllib.request.urlopen()` (no external dependency)
  - Log each attempt: "Health check attempt N... waiting"
- All subprocess calls use `subprocess.run()` with `capture_output=True`, `text=True`

**Tests:**
- Unit: `tests/unit/test_sandbox_lifecycle.py`
  - `test_start_command_construction`: verify correct docker compose command with absolute paths
  - `test_stop_uses_slot_compose`: verify stop uses slot dir's compose copy, not worktree's
  - `test_health_gate_success`: mock HTTP response 200 → returns True
  - `test_health_gate_timeout`: mock connection refused → returns False after timeout
  - `test_health_gate_url_construction`: correct URL from config + slot ports
  - `test_start_failure_runs_down`: mock compose up failing → compose down called

**Acceptance Criteria:**
- [ ] Start uses worktree's compose file (absolute path)
- [ ] Stop uses slot dir's compose copy (absolute path)
- [ ] Health gate polls correctly with configurable timeout
- [ ] Failed start triggers cleanup (compose down)
- [ ] All subprocess commands use absolute paths

---

## Task 2.5: CLI impl command

**File(s):**
- `src/devops_ai/cli/impl.py` (create)
- `src/devops_ai/cli/main.py` (modify — register impl)
- `tests/unit/test_cli_impl.py` (create)

**Type:** CODING
**Task Categories:** API Endpoint (CLI), State Machine, Cross-Component

**Description:**
Implement `kinfra impl <feature/milestone>` — the core command that creates an implementation worktree and optionally starts a sandbox.

**Implementation Notes:**
- Parse `<feature/milestone>` argument: split on `/`
- Load config (optional — works without for worktree-only)
- Find milestone file: glob `docs/designs/<feature>/implementation/<milestone>_*.md`
  - If not found: error with helpful message
- Check worktree doesn't already exist
- **If config has sandbox section:**
  1. Load registry
  2. Clean stale entries
  3. Allocate slot (find free, TCP bind test)
  4. Create worktree (git worktree add)
  5. Create slot dir
  6. Claim slot in registry
  7. Copy compose file to slot dir
  8. Generate .env.sandbox
  9. Generate override
  10. Start sandbox (docker compose up)
  11. Run health gate
  12. On Docker failure: release slot, remove slot dir, keep worktree
  13. Report: URLs, slot info
- **If no sandbox section (or no config):**
  1. Create worktree only
  2. Report: worktree path, branch

**Tests:**
- Unit: `tests/unit/test_cli_impl.py`
  - `test_parse_feature_milestone`: "wellness-reminders/M1" → feature, milestone
  - `test_milestone_not_found`: error message
  - `test_worktree_already_exists`: error message
  - `test_impl_without_config_creates_worktree`: worktree only, no sandbox
  - `test_impl_with_config_allocates_slot`: slot claimed in registry
  - `test_impl_docker_failure_releases_slot`: slot released, worktree kept

**Acceptance Criteria:**
- [ ] Feature/milestone parsing correct
- [ ] Milestone file validation works
- [ ] With sandbox config: full slot allocation + Docker lifecycle
- [ ] Without sandbox config: worktree only (no error)
- [ ] Docker failure: slot released, worktree preserved
- [ ] Health gate result reported (warning if timeout)

---

## Task 2.6: CLI done extended + status

**File(s):**
- `src/devops_ai/cli/done.py` (modify — add sandbox cleanup)
- `src/devops_ai/cli/status.py` (create)
- `src/devops_ai/cli/main.py` (modify — register status)
- `tests/unit/test_cli_done_sandbox.py` (create)

**Type:** CODING
**Task Categories:** API Endpoint (CLI), State Machine

**Description:**
Extend `kinfra done` to handle impl worktrees with sandboxes: stop containers, remove slot dir, release slot. Critical: stop containers BEFORE removing worktree. Also implement `kinfra status` to show current sandbox details.

**Implementation Notes:**
- `kinfra done <name> [--force]` (extended from M1):
  - Find worktree by partial name (search registry first, then git worktree list)
  - If slot found in registry:
    1. Check dirty (unless --force)
    2. Stop sandbox: `stop_sandbox(slot)` — uses slot dir's compose copy
    3. Remove slot dir: `remove_slot_dir()`
    4. Release slot in registry
    5. Remove worktree: `remove_worktree()`
    6. Report: slot released, worktree removed
  - If no slot (spec worktree): same as M1 (just remove worktree)
  - Handle partial state: slot dir missing → skip Docker stop, still release registry + remove worktree (GAP-17)
- `kinfra status`:
  - Find project root (walk up)
  - Check if current directory is inside a worktree
  - If so, find slot in registry
  - Display: project, feature, milestone, slot number, ports, container status
  - If no sandbox: "No sandbox running in current directory"

**Tests:**
- Unit: `tests/unit/test_cli_done_sandbox.py`
  - `test_done_with_sandbox_stops_containers`: Docker compose down called
  - `test_done_removes_slot_dir`: slot dir deleted
  - `test_done_releases_slot`: registry entry removed
  - `test_done_ordering`: stop containers before remove worktree
  - `test_done_missing_slot_dir`: graceful skip, still cleans registry + worktree
  - `test_done_spec_worktree_no_sandbox`: same as M1 behavior

**Acceptance Criteria:**
- [ ] `done` stops sandbox containers before removing worktree
- [ ] `done` removes slot directory and releases registry entry
- [ ] `done` handles partial state (missing slot dir) gracefully
- [ ] `done` still works for spec worktrees (no sandbox)
- [ ] `status` shows sandbox details for current directory
- [ ] `status` handles "not in a sandbox" case

---

## Task 2.7: M2 E2E verification

**Type:** VALIDATION

**Description:**
Validate the full sandbox lifecycle works end-to-end.

**Test Steps:**

```bash
# 1. Setup: create a test project with a simple compose
mkdir -p /tmp/test-kinfra-m2 && cd /tmp/test-kinfra-m2
git init && git commit --allow-empty -m "init"

# Create a minimal compose with a simple service
cat > docker-compose.yml << 'EOF'
services:
  myapp:
    image: python:3.12-slim
    command: python -m http.server 8080
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080')"]
      interval: 5s
      timeout: 3s
      retries: 3
EOF
git add . && git commit -m "add compose"

# Create design + milestone structure
mkdir -p docs/designs/my-feature/implementation
echo "# M1 Foundation" > docs/designs/my-feature/implementation/M1_foundation.md
git add . && git commit -m "add milestone"

# 2. Initialize
kinfra init
# Answer prompts: name=test-m2, prefix=test-m2, health=/  (or skip health), code dirs=[]

# 3. Verify no worktrees
kinfra worktrees
# Expected: empty or just main

# 4. Create impl worktree with sandbox
kinfra impl my-feature/M1
# Expected: worktree created, slot claimed, containers started

# 5. Verify sandbox running
kinfra status
# Expected: slot number, port (8081), running

# 6. Verify port offset
curl -s http://localhost:8081 > /dev/null && echo "Port offset works"

# 7. List worktrees
kinfra worktrees
# Expected: my-feature/M1 shown as impl with slot info

# 8. Cleanup
kinfra done my-feature-M1 --force
# Expected: containers stopped, slot released, worktree removed

# 9. Verify cleanup
kinfra worktrees
# Expected: empty
cat ~/.devops-ai/registry.json
# Expected: no slots claimed

# 10. Teardown
cd / && rm -rf /tmp/test-kinfra-m2
```

**Success Criteria:**
- [ ] `kinfra impl` creates worktree with sandbox on offset port
- [ ] Service accessible on offset port (base + slot_id)
- [ ] `kinfra status` shows sandbox details
- [ ] `kinfra done` cleanly stops containers, releases slot, removes worktree
- [ ] Registry is clean after done
- [ ] Previous milestone (M1) E2E tests still pass

### Completion Checklist

- [ ] All tasks complete and committed
- [ ] Unit tests pass: `uv run pytest tests/unit`
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`
- [ ] E2E test passes (above)
- [ ] M1 E2E test still passes
- [ ] No regressions introduced
