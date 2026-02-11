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

**Next Task Notes (3.3):**
- Import `ObservabilityManager` and constants from `devops_ai.observability`
- `sandbox.py` has `_observability_network_exists()` which should be removed — Task 3.3 replaces the conditional check with always-on observability
- The existing `generate_override()` conditionally adds observability; Task 3.3 makes it unconditional
