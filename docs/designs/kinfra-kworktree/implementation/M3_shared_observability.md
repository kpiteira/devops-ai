---
design: docs/designs/kinfra-kworktree/DESIGN.md
architecture: docs/designs/kinfra-kworktree/ARCHITECTURE.md
---

# Milestone 3: Shared Observability — Jaeger + Grafana + Prometheus for all sandboxes

**Goal:** A developer's sandbox traces appear in a shared Jaeger instance without any per-project observability setup. `kinfra impl` auto-starts the shared stack, and sandboxes automatically connect via the `devops-ai-observability` Docker network.

**Branch:** `impl/kinfra-kworktree-M3`
**Builds on:** Milestone 2

---

## Task 3.1: Observability compose template

**File(s):**
- `templates/observability/docker-compose.yml` (create)
- `tests/unit/test_observability_template.py` (create)

**Type:** CODING
**Task Categories:** Configuration

**Description:**
Create the Docker Compose template for the shared observability stack: Jaeger all-in-one, Grafana, and Prometheus. Uses dedicated host ports in the 4xxxx range to avoid conflicts with ktrdr's standard and offset ports. Container names are prefixed with `devops-ai-` to avoid collision with project containers.

**Implementation Notes:**
- Services:
  - `devops-ai-jaeger`: `jaegertracing/jaeger:latest`
    - OTLP gRPC receiver on internal 4317 → host 44317
    - UI on internal 16686 → host 46686
    - `COLLECTOR_OTLP_ENABLED=true`
  - `devops-ai-grafana`: `grafana/grafana:latest`
    - UI on internal 3000 → host 43000
    - Provisioned with Jaeger as default data source (via environment or provisioning volume)
  - `devops-ai-prometheus`: `prom/prometheus:latest`
    - HTTP on internal 9090 → host 49090
- All services join the `devops-ai-observability` network (declared as external)
- Container names explicitly set: `container_name: devops-ai-jaeger`, etc.
- Use `restart: unless-stopped` for all services (lightweight, intended always-running)
- Template includes header comments explaining purpose and port choices
- Keep it minimal — no custom dashboards or scrape configs in M3 (can enhance later)

**Tests:**
- Unit: `tests/unit/test_observability_template.py`
  - `test_template_is_valid_yaml`: parses without error
  - `test_template_services`: contains exactly 3 services with expected names
  - `test_template_ports_in_4xxxx_range`: all host ports are in 4xxxx range
  - `test_template_container_names`: all prefixed with `devops-ai-`
  - `test_template_network_external`: `devops-ai-observability` declared as external
  - `test_template_otlp_enabled`: Jaeger has OTLP collector enabled

**Acceptance Criteria:**
- [ ] Template parses as valid Docker Compose YAML
- [ ] Three services: devops-ai-jaeger, devops-ai-grafana, devops-ai-prometheus
- [ ] Host ports: 46686, 44317, 43000, 49090 (no ktrdr conflicts)
- [ ] All containers named with `devops-ai-` prefix
- [ ] External network `devops-ai-observability` declared
- [ ] Jaeger has OTLP gRPC collector enabled

---

## Task 3.2: Observability Manager

**File(s):**
- `src/devops_ai/observability.py` (create)
- `tests/unit/test_observability.py` (create)

**Type:** CODING
**Task Categories:** External, State Machine

**Description:**
Implement the Observability Manager that handles lifecycle of the shared observability stack: ensure Docker network exists, copy template to `~/.devops-ai/observability/`, start/stop via Docker Compose, report status and endpoints.

**Implementation Notes:**
- `ensure_network()`:
  - `docker network inspect devops-ai-observability` — if not found, `docker network create devops-ai-observability`
  - Idempotent — safe to call multiple times
- `ensure_compose_file()`:
  - Check if `~/.devops-ai/observability/docker-compose.yml` exists
  - If not: copy from `templates/observability/docker-compose.yml`
  - Find template location: relative to package install path (use `importlib.resources` or `__file__`)
- `start()`:
  - `ensure_network()`
  - `ensure_compose_file()`
  - `docker compose -f ~/.devops-ai/observability/docker-compose.yml up -d`
  - Wait briefly for services to be reachable (poll Jaeger UI at localhost:46686, timeout 30s)
- `stop()`:
  - `docker compose -f ~/.devops-ai/observability/docker-compose.yml down`
  - Do NOT remove the network (other sandboxes may be connected)
- `ensure_running()`:
  - Check if services are running: `docker compose -f <path> ps --format json`
  - If all 3 services running: return immediately
  - If any not running: call `start()`
  - Used by `kinfra impl` for auto-start
- `status()` → `ObservabilityStatus`:
  - Check each service: running/stopped/not-found
  - Return service states + endpoint URLs
- `get_endpoints()` → `dict[str, str]`:
  - `{"jaeger_ui": "http://localhost:46686", "jaeger_otlp": "http://localhost:44317", "grafana": "http://localhost:43000", "prometheus": "http://localhost:49090"}`
- All subprocess calls use absolute path to compose file

**Tests:**
- Unit: `tests/unit/test_observability.py`
  - `test_ensure_network_command`: correct `docker network create` command
  - `test_ensure_compose_copies_template`: template copied to expected path
  - `test_ensure_compose_idempotent`: existing file not overwritten
  - `test_start_command`: correct `docker compose up -d` with absolute path
  - `test_stop_command`: correct `docker compose down` with absolute path
  - `test_get_endpoints`: correct URLs with 4xxxx ports
  - `test_status_all_running`: mock `docker compose ps` → all running
  - `test_status_partial`: mock → some stopped
  - `test_ensure_running_already_up`: does not call start if all running
  - `test_ensure_running_starts_if_down`: calls start when not all running

**Acceptance Criteria:**
- [ ] Docker network created idempotently
- [ ] Template copied to `~/.devops-ai/observability/` on first use
- [ ] Start/stop use absolute paths for compose invocation
- [ ] `ensure_running()` is idempotent (no-op when already up)
- [ ] Status reports per-service state
- [ ] Endpoints return correct 4xxxx port URLs

---

## Task 3.3: Override generator — observability integration

**File(s):**
- `src/devops_ai/sandbox.py` (modify — update `generate_override()`)
- `tests/unit/test_sandbox.py` (modify — add observability tests)

**Type:** CODING
**Task Categories:** Cross-Component

**Description:**
Update the override generator (from M2 Task 2.3) to fully integrate observability: join the `devops-ai-observability` network and set OTEL environment variables. In M2, observability support was conditional (only if network exists). Now that the Observability Manager guarantees the network exists during `impl`, the override always includes observability configuration.

**Implementation Notes:**
- The `generate_override()` function now always includes:
  - `networks:` section declaring `devops-ai-observability: external: true`
  - For each target service:
    - `networks: [default, devops-ai-observability]`
    - `environment:` with OTEL vars
- OTEL environment variables (per config or defaults):
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://devops-ai-jaeger:4317` (uses container name, not localhost — traffic flows over Docker network)
  - `OTEL_RESOURCE_ATTRIBUTES=service.namespace=<project>-slot-<slot_id>`
- If `[sandbox.otel]` section exists in infra.toml:
  - Use `endpoint_var` for the env var name (default `OTEL_EXPORTER_OTLP_ENDPOINT`)
  - Use `namespace_var` for namespace (default `OTEL_RESOURCE_ATTRIBUTES`)
- The conditional check from M2 (`docker network inspect`) is removed — `kinfra impl` now calls `ensure_running()` before generating overrides, so the network is guaranteed

**Tests:**
- Unit: `tests/unit/test_sandbox.py` (add to existing)
  - `test_override_includes_observability_network`: `devops-ai-observability` in networks section
  - `test_override_otel_endpoint`: correct OTEL endpoint env var pointing to devops-ai-jaeger
  - `test_override_otel_namespace`: namespace matches `<project>-slot-<N>` pattern
  - `test_override_custom_otel_vars`: config with `[sandbox.otel]` uses custom var names
  - `test_override_services_join_observability`: target services have both `default` and `devops-ai-observability` networks

**Acceptance Criteria:**
- [ ] Override YAML includes `devops-ai-observability` external network
- [ ] OTEL endpoint points to `devops-ai-jaeger:4317` (container name)
- [ ] OTEL namespace is `<project>-slot-<N>`
- [ ] Custom OTEL var names from `[sandbox.otel]` honored
- [ ] All target services join both `default` and `devops-ai-observability` networks

---

## Task 3.4: CLI observability commands + impl auto-start

**File(s):**
- `src/devops_ai/cli/observability.py` (create)
- `src/devops_ai/cli/impl.py` (modify — add `ensure_running()` call)
- `src/devops_ai/cli/main.py` (modify — register observability subcommand)
- `tests/unit/test_cli_observability.py` (create)

**Type:** CODING
**Task Categories:** API Endpoint (CLI), Cross-Component

**Description:**
Implement the `kinfra observability` subcommand group (`up`, `down`, `status`) and integrate auto-start into `kinfra impl`. When `impl` runs with a sandbox config, it calls `ensure_running()` before slot allocation to guarantee the observability network and services are available.

**Implementation Notes:**
- `kinfra observability up`:
  - Call `observability.start()`
  - Report endpoints on success
  - If already running: "Observability stack already running."
- `kinfra observability down`:
  - Call `observability.stop()`
  - Warn if sandboxes are still running (check registry for any claimed slots with status "running")
  - "Observability stack stopped. Note: N sandbox(es) still running — their traces won't reach Jaeger."
- `kinfra observability status`:
  - Call `observability.status()`
  - Display Rich table with service name, status, endpoint URL
- Modify `kinfra impl` (in `impl.py`):
  - After loading config, before slot allocation:
    ```
    if config.has_sandbox:
        observability.ensure_running()
    ```
  - If `ensure_running()` fails (Docker not running, etc.): warn but continue (non-fatal — sandbox can still work, just no traces)
- Use Typer sub-app: `observability_app = typer.Typer()`, register as `app.add_typer(observability_app, name="observability")`

**Tests:**
- Unit: `tests/unit/test_cli_observability.py`
  - `test_observability_up_starts_stack`: start called
  - `test_observability_up_already_running`: appropriate message
  - `test_observability_down_warns_active_sandboxes`: warning with count
  - `test_observability_status_display`: correct table output
  - `test_impl_calls_ensure_running`: mock `ensure_running()`, verify called during impl
  - `test_impl_ensure_running_failure_non_fatal`: failure logged as warning, impl continues

**Acceptance Criteria:**
- [ ] `kinfra observability up` starts the shared stack and reports endpoints
- [ ] `kinfra observability down` stops with sandbox warning
- [ ] `kinfra observability status` shows per-service health
- [ ] `kinfra impl` auto-starts observability when sandbox config present
- [ ] Observability failure during `impl` is non-fatal (warning only)

---

## Task 3.5: M3 E2E verification

**Type:** VALIDATION

**Description:**
Validate that sandbox traces appear in the shared Jaeger instance.

**Test Steps:**

```bash
# 1. Setup: create a test project with a traceable service
mkdir -p /tmp/test-kinfra-m3 && cd /tmp/test-kinfra-m3
git init && git commit --allow-empty -m "init"

# Create a simple Python app that sends OTEL traces
cat > app.py << 'PYEOF'
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
import http.server
import os

resource = Resource.create({
    "service.name": "test-app",
    "service.namespace": os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "unknown").split("=")[-1]
})
provider = TracerProvider(resource=resource)
exporter = OTLPSpanExporter(endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"), insecure=True)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        with tracer.start_as_current_span("handle-request"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

http.server.HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
PYEOF

cat > Dockerfile << 'EOF'
FROM python:3.12-slim
RUN pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
COPY app.py /app/app.py
CMD ["python", "/app/app.py"]
EOF

cat > docker-compose.yml << 'EOF'
services:
  myapp:
    build: .
    ports:
      - "${TEST_M3_PORT:-8080}:8080"
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4317}
      - OTEL_RESOURCE_ATTRIBUTES=${OTEL_RESOURCE_ATTRIBUTES:-service.namespace=default}
EOF
git add . && git commit -m "add traceable app"

# Create design + milestone
mkdir -p docs/designs/my-feature/implementation
echo "# M1" > docs/designs/my-feature/implementation/M1_foundation.md
git add . && git commit -m "add milestone"

# 2. Initialize
kinfra init
# Answer prompts: name=test-m3, health=/, code dirs=[]

# 3. Verify observability is not yet running
kinfra observability status
# Expected: not running or not found

# 4. Start observability manually
kinfra observability up
# Expected: stack started, endpoints reported

# 5. Verify endpoints
curl -s http://localhost:46686 | head -c 100
# Expected: Jaeger UI HTML

# 6. Create impl with sandbox
kinfra impl my-feature/M1
# Expected: observability already running (no restart), sandbox started

# 7. Hit the service to generate traces
curl http://localhost:8081
# Expected: 200 OK

# 8. Wait for trace export (BatchSpanProcessor has a delay)
sleep 5

# 9. Check Jaeger for traces
curl -s "http://localhost:46686/api/traces?service=test-app&limit=1" | python3 -c "
import json, sys
data = json.load(sys.stdin)
traces = data.get('data', [])
if traces:
    print(f'Found {len(traces)} trace(s) - PASS')
else:
    print('No traces found - FAIL')
    sys.exit(1)
"

# 10. Cleanup
kinfra done my-feature-M1 --force
kinfra observability down

# 11. Teardown
cd / && rm -rf /tmp/test-kinfra-m3
```

**Success Criteria:**
- [ ] `kinfra observability up` starts Jaeger/Grafana/Prometheus on 4xxxx ports
- [ ] `kinfra observability status` shows all services running
- [ ] `kinfra impl` auto-starts observability if not running
- [ ] Sandbox containers connect to `devops-ai-observability` network
- [ ] OTEL traces from sandbox appear in shared Jaeger
- [ ] Traces are namespaced by `service.namespace=<project>-slot-<N>`
- [ ] `kinfra observability down` stops the shared stack
- [ ] Previous milestones (M1, M2) E2E tests still pass

### Completion Checklist

- [ ] All tasks complete and committed
- [ ] Unit tests pass: `uv run pytest tests/unit`
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`
- [ ] E2E test passes (above)
- [ ] M1 + M2 E2E tests still pass
- [ ] No regressions introduced
