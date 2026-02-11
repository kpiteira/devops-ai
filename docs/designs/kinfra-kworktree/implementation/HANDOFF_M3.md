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

**Next Task Notes (3.5 — VALIDATION):**
- All CLI commands registered: `kinfra observability up|down|status`
- `kinfra impl` auto-starts observability when config.has_sandbox is true
- E2E should test real Docker lifecycle — Jaeger/Grafana/Prometheus on 4xxxx ports
