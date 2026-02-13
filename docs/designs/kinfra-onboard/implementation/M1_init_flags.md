---
design: ../DESIGN.md
architecture: ../ARCHITECTURE.md
---

# Milestone 1: kinfra init --dry-run and --auto

**Goal:** `kinfra init` supports `--dry-run`, `--auto`, and `--health-endpoint` flags, enabling non-interactive and preview modes.

---

## Task 1.1: Refactor init_command() to separate detection from interaction

**File(s):** `src/devops_ai/cli/init_cmd.py`
**Type:** CODING
**Estimated time:** 1-2 hours

**Description:**
Extract the detection pipeline from `init_command()` into a pure function that returns a structured result, separate from the interactive prompts and file writing. This enables --dry-run and --auto to reuse the same detection logic.

**Implementation Notes:**

Create a dataclass `InitPlan` that holds all detected/decided values:
```python
@dataclass
class InitPlan:
    project_root: Path
    project_name: str
    prefix: str
    compose_file: str
    compose_path: Path
    services: dict[str, dict[str, Any]]
    obs_services: list[str]
    app_services: dict[str, dict[str, Any]]
    ports: dict[str, int]
    health_endpoint: str | None
    health_port_var: str | None
    toml_content: str  # generated infra.toml string
```

Extract a `detect_project(project_root: Path) -> InitPlan` function that:
1. Finds compose files
2. Parses services
3. Identifies obs services
4. Detects project name
5. Builds port map
6. Generates toml content
Uses defaults for all values (first compose file, detected name as prefix, `/api/v1/health` as health endpoint).

The existing `init_command()` remains the interactive path — it calls `detect_project()` then overrides values via `typer.prompt()` before writing.

**Tests:** `tests/unit/test_cli_init.py`
- [ ] `detect_project()` returns correct InitPlan for compose with app + Jaeger
- [ ] `detect_project()` handles compose with no obs services
- [ ] `detect_project()` handles no compose file (compose_path doesn't exist)
- [ ] `detect_project()` handles empty compose (no services key)
- [ ] Existing tests still pass (interactive flow unchanged)

**Acceptance Criteria:**
- [ ] `detect_project()` is a pure function (no prompts, no file writes)
- [ ] `init_command()` interactive flow unchanged
- [ ] All existing tests pass
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`

---

## Task 1.2: Add --dry-run, --auto, and --health-endpoint flags

**File(s):** `src/devops_ai/cli/init_cmd.py`, `src/devops_ai/cli/main.py`
**Type:** CODING
**Estimated time:** 1-2 hours

**Description:**
Add three flags to `kinfra init`:
- `--dry-run`: Run detection, print plan to stdout, write nothing
- `--auto`: Accept all detected defaults, skip all prompts
- `--health-endpoint TEXT`: Override the default health endpoint (useful with --auto)

**Implementation Notes:**

Update `init_command()` signature:
```python
def init_command(
    project_root: Path | None = None,
    dry_run: bool = False,
    auto: bool = False,
    health_endpoint: str | None = None,
) -> int:
```

Logic flow:
1. Call `detect_project()` to get the InitPlan
2. If `health_endpoint` is provided, override the plan's health endpoint
3. If not `auto`: prompt for overrides (current behavior)
4. If `auto` and existing config: auto-confirm update
5. If `dry_run`: print formatted plan to stdout, return 0
6. Otherwise: write infra.toml and rewrite compose (current behavior)

Wire in `main.py`:
```python
@app.command()
def init(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
    auto: bool = typer.Option(False, "--auto", help="Accept defaults, no prompts"),
    health_endpoint: str | None = typer.Option(None, "--health-endpoint", help="Override health check endpoint"),
) -> None:
    code = init_command(dry_run=dry_run, auto=auto, health_endpoint=health_endpoint)
    raise typer.Exit(code)
```

Dry-run output format (plain text, not YAML — easy to read in terminal and capture by skill):
```
Project: wellness-agent
Prefix: wellness-agent
Compose: docker-compose.yml

Services detected:
  wellness-agent: ports [8080]
  jaeger: ports [14686, 14317] (observability — will be commented out)

Planned infra.toml:
  [project]
  name = "wellness-agent"
  prefix = "wellness-agent"
  ...

Compose changes:
  - Parameterize port 8080 → ${WELLNESS_AGENT_WELLNESS_AGENT_PORT:-8080}
  - Comment out service: jaeger
  - Remove depends_on: jaeger
  - Add kinfra header comment
  - Backup: docker-compose.yml.bak

No files written (dry run).
```

**Tests:** `tests/unit/test_cli_init.py`
- [ ] `--dry-run --auto`: detection runs, output printed, no files created (no infra.toml, no compose changes, no .bak)
- [ ] `--auto`: uses detected defaults, creates infra.toml and rewrites compose without prompts
- [ ] `--auto` with existing config: auto-confirms update
- [ ] `--auto --health-endpoint /health`: uses provided endpoint instead of default
- [ ] `--dry-run` alone (without --auto): still prompts for values, then previews (no writes)
- [ ] Existing interactive tests still pass

**Acceptance Criteria:**
- [ ] `kinfra init --dry-run --auto` produces formatted output and writes nothing
- [ ] `kinfra init --auto` completes without any prompts
- [ ] `kinfra init --health-endpoint /custom/health --auto` uses the provided endpoint
- [ ] Interactive mode (no flags) unchanged
- [ ] All tests pass
- [ ] Quality gates pass

---

## Task 1.3: E2E verification

**Type:** VALIDATION
**Estimated time:** 15 min

**Description:**
Validate M1 is complete by running `kinfra init --dry-run --auto` against a real project directory.

**Test Steps:**

```bash
# 1. Create a test project directory
mkdir -p /tmp/kinfra-test && cd /tmp/kinfra-test
git init
cat > docker-compose.yml << 'EOF'
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
  jaeger:
    image: jaegertracing/jaeger:latest
    ports:
      - "16686:16686"
      - "4317:4317"
EOF
cat > pyproject.toml << 'EOF'
[project]
name = "test-project"
EOF

# 2. Dry run — should print plan, write nothing
kinfra init --dry-run --auto
# Verify: output shows test-project, ports, obs services
# Verify: no .devops-ai/infra.toml created
ls .devops-ai/infra.toml 2>/dev/null && echo "FAIL: files written" || echo "OK: no files"

# 3. Auto run — should create files without prompts
kinfra init --auto
# Verify: .devops-ai/infra.toml exists
cat .devops-ai/infra.toml
# Verify: compose parameterized
grep '${' docker-compose.yml
# Verify: jaeger commented out
grep '# jaeger:' docker-compose.yml
# Verify: backup exists
ls docker-compose.yml.bak

# 4. Re-run auto — should update without prompts
kinfra init --auto --health-endpoint /custom/health
cat .devops-ai/infra.toml | grep custom

# 5. Cleanup
rm -rf /tmp/kinfra-test
```

**Success Criteria:**
- [ ] `--dry-run --auto` prints plan, creates no files
- [ ] `--auto` creates infra.toml and rewrites compose with no interaction
- [ ] `--auto` re-run updates existing config
- [ ] `--health-endpoint` override works
- [ ] All unit tests pass: `uv run pytest tests/unit`
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`

---

## Milestone 1 Completion Checklist

- [ ] All tasks complete and committed
- [ ] Unit tests pass: `uv run pytest tests/unit`
- [ ] E2E verification passes (above)
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`
- [ ] No regressions in existing kinfra commands
