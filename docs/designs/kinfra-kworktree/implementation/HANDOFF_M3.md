# Handoff — Milestone 3: Shared Observability

## Task 3.1 Complete: Observability Compose Template

**Approach:** Created `templates/observability/docker-compose.yml` with 3 services (Jaeger, Grafana, Prometheus) on 4xxxx host ports, all joining the external `devops-ai-observability` network.

**Key decisions:**
- Used `ruamel.yaml` in tests (project dependency) rather than PyYAML
- Grafana provisioned with anonymous admin access for dev convenience (no login required)
- Template at repo root `templates/` (not inside Python package) — Task 3.2 will need to locate it via `__file__` or `importlib.resources`

## Task 3.2 Complete: Observability Manager

**Approach:** `ObservabilityManager` class with `base_dir` injection for testability. Template discovered by walking parent dirs from `__file__` — works for editable installs (`uv run`).

**Key decisions:**
- `_find_template()` walks up from `observability.py` to find `templates/observability/docker-compose.yml` at repo root — good enough for dev usage; wheel distribution would need package data
- `status()` parses `docker compose ps --format json` — handles both list and single-object JSON formats
- `ensure_running()` checks status first, only calls `start()` if not all 3 services are running
- `_wait_for_jaeger()` polls Jaeger UI with 30s timeout after compose up

## Task 3.3 Complete: Override Generator — Observability Integration

**Approach:** Removed `_observability_network_exists()` conditional. Override now always includes `devops-ai-observability` network + OTEL env vars. Added `otel_endpoint_var`/`otel_namespace_var` to `InfraConfig` with defaults, parsed from `[sandbox.otel]` in infra.toml.

**Gotchas:**
- Existing tests all patched `_observability_network_exists` — had to remove all those patches when making observability unconditional
- `OTEL_ENDPOINT` constant extracted to module level in `sandbox.py` for reuse

## Task 3.4 Complete: CLI Observability Commands + impl Auto-Start

**Approach:** Typer sub-app `observability_app` with `obs_up`, `obs_down`, `obs_status` commands mapped to `_up_command()`, `_down_command()`, `_status_command()` functions. `impl.py` calls `ObservabilityManager().ensure_running()` before sandbox setup (wrapped in try/except for non-fatal).

**Gotchas:**
- `logger = logging.getLogger(__name__)` must go after all imports (ruff E402)
- Typer sub-app commands need distinct function names (`obs_up` not `up`) to avoid shadowing builtins

## Task 3.5 Complete: M3 E2E Verification

**E2E test:** observability-trace-flow — PASSED (11 steps)

**Full E2E flow executed:**
1. Created test project with OTEL-instrumented Python app + Dockerfile + compose
2. Set up `.devops-ai/infra.toml` with sandbox config (port, health, code mount)
3. Verified observability not running initially
4. `kinfra observability up` → Jaeger/Grafana/Prometheus started on 4xxxx ports
5. `kinfra impl my-feature/M1` → worktree created, sandbox started on slot 1 (port 8081)
6. Verified override has `devops-ai-observability` network + OTEL env vars
7. Verified sandbox container (`test-m3-slot-1-myapp-1`) joined observability network
8. Sent HTTP requests to sandbox → traces generated
9. Queried Jaeger API → **5 traces found**, operation=`handle-request`, `service.namespace=test-m3-slot-1`
10. `kinfra done my-feature-M1 --force` → worktree + sandbox cleaned up
11. `kinfra observability down` → stack stopped, test project removed

**Fixes found during validation:**
- `docker compose ps --format json` outputs NDJSON (one object per line), not a JSON array — fixed parser to handle both formats
- Typer sub-app command names defaulted to function names (`obs-up`) — added explicit `name="up"` params
