---
design: docs/designs/sandbox-provisioning/DESIGN.md
architecture: docs/designs/sandbox-provisioning/ARCHITECTURE.md
---

# Milestone 2: Discovery

**Goal:** `kinfra init` detects undeclared environment variables and gitignored volume mounts in compose files, and proposes the correct `[sandbox.secrets]`, `[sandbox.env]`, and `[sandbox.files]` sections for `infra.toml`.

---

## Task 2.1: Env var and volume mount detection

**File(s):** `src/devops_ai/cli/init_cmd.py`
**Type:** CODING
**Estimated time:** 2 hours

**Description:**
Add two pure detection functions and their supporting dataclasses. These find compose references that aren't covered by existing infra.toml config — env vars that need `[sandbox.secrets]` or `[sandbox.env]`, and volume mounts that need `[sandbox.files]`.

**Implementation Notes:**

**Env var detection:**

```python
@dataclass
class EnvVarCandidate:
    name: str
    services: list[str]     # which services reference it
    default: str | None     # from ${VAR:-default}, if present

def detect_env_vars(
    compose_content: str,
    known_vars: set[str],
) -> list[EnvVarCandidate]:
```

Parse `${VAR}` and `${VAR:-default}` from raw compose text using regex:
```python
re.findall(r'\$\{([A-Z_][A-Z0-9_]*)(?::-(.*?))?\}', compose_content)
```

Use raw text (not YAML-parsed) to catch references in all contexts — environment, command, labels, etc.

`known_vars` is the set of port vars + OTEL vars + `COMPOSE_PROJECT_NAME` — these are already handled by kinfra and should be excluded.

To identify which services reference each var, parse the YAML and check each service's `environment` block. For vars found only in non-environment contexts (command, labels), service attribution is "unknown".

**Gitignored volume mount detection:**

```python
@dataclass
class FileMountCandidate:
    host_path: str          # relative to project root
    container_path: str     # inside container
    service: str            # which service mounts it
    source_exists: bool     # does the file exist in main repo?
    example_exists: bool    # does a .example variant exist?
    example_path: str | None

def detect_gitignored_mounts(
    compose_content: str,
    project_root: Path,
) -> list[FileMountCandidate]:
```

Steps:
1. Parse compose YAML for bind mounts — look for volume entries matching `./path:/container/path` or `path:/container/path` (not named volumes)
2. For each host path, run `git check-ignore -q <path>` via subprocess (exit 0 = ignored)
3. If ignored: build `FileMountCandidate` with source existence check and `.example` variant check

Named volumes (no `/` in host part, or declared in top-level `volumes:`) are not bind mounts — skip them.

**Extend InitPlan:**

```python
@dataclass
class InitPlan:
    # ... existing fields ...
    env_var_candidates: list[EnvVarCandidate] = field(default_factory=list)
    file_mount_candidates: list[FileMountCandidate] = field(default_factory=list)
```

Call both detection functions in `detect_project()` after existing detection:
```python
known_vars = set(ports.keys()) | {"COMPOSE_PROJECT_NAME", otel_endpoint_var, otel_namespace_var}
env_var_candidates = detect_env_vars(compose_path.read_text(), known_vars)
file_mount_candidates = detect_gitignored_mounts(compose_path.read_text(), project_root)
```

**Tests:** `tests/unit/test_cli_init.py`
- [ ] `detect_env_vars()` finds `${VAR}` references in environment sections
- [ ] `detect_env_vars()` finds `${VAR:-default}` and extracts default value
- [ ] `detect_env_vars()` excludes known port vars
- [ ] `detect_env_vars()` excludes OTEL vars and COMPOSE_PROJECT_NAME
- [ ] `detect_env_vars()` identifies which services reference each var
- [ ] `detect_env_vars()` handles compose with no env var references
- [ ] `detect_gitignored_mounts()` identifies gitignored bind mounts (mock `git check-ignore`)
- [ ] `detect_gitignored_mounts()` skips named volumes
- [ ] `detect_gitignored_mounts()` checks source existence and .example variant
- [ ] `detect_gitignored_mounts()` handles compose with no bind mounts
- [ ] `detect_project()` populates new InitPlan fields

**Acceptance Criteria:**
- [ ] Both detection functions are pure (git check-ignore is subprocess but deterministic)
- [ ] Existing detect_project() behavior unchanged
- [ ] All existing tests pass
- [ ] Quality gates pass

---

## Task 2.2: Integration with init flow

**File(s):** `src/devops_ai/cli/init_cmd.py`
**Type:** CODING
**Estimated time:** 2 hours

**Description:**
Wire detection results into the init command — `--check` mode reports gaps, interactive mode prompts for resolution type, `--auto` mode generates complete infra.toml with provisioning sections.

**Implementation Notes:**

**`--check` mode extension:**

When `--check` is used on an already-onboarded project, report detected env vars and mounts:

```
Project: wellness-agent (already onboarded)

⚠ Undeclared environment variables in compose:
  TELEGRAM_BOT_TOKEN (wellness-agent service)

⚠ Gitignored volume mounts without [sandbox.files]:
  config.yaml → wellness-agent (./config.yaml:/app/config.yaml:ro)

Suggested additions to .devops-ai/infra.toml:

  [sandbox.secrets]
  TELEGRAM_BOT_TOKEN = "$TELEGRAM_BOT_TOKEN"   # or op://vault/item/field

  [sandbox.files]
  "config.yaml" = "config.yaml"
```

Note: `--check` already partially exists via `kinfra-onboard` skill's Phase 1. This extends it to cover env vars and files.

**Interactive mode extension:**

After port/health prompts, for each detected env var:
```
Environment variables detected in compose (not ports):
  TELEGRAM_BOT_TOKEN (wellness-agent service)

? How should TELEGRAM_BOT_TOKEN be provided?
  1. Host environment variable ($TELEGRAM_BOT_TOKEN) [default]
  2. 1Password reference (op://vault/item/field)
  3. Literal value (committed to git — dev defaults only)
  4. Skip (don't add to infra.toml)
```

For each detected gitignored mount:
```
Gitignored files mounted as volumes:
  config.yaml → wellness-agent (./config.yaml:/app/config.yaml:ro)

? Source for config.yaml in sandboxes?
  1. Copy from main repo (config.yaml — exists) [default]
  2. Copy from template (config.yaml.example — exists)
  3. Skip
```

**`--auto` mode extension:**

Auto-select defaults:
- Env vars → `$VAR_NAME` (host environment)
- Gitignored mounts → copy from main repo if source exists, skip otherwise

**Extended `generate_infra_toml()`:**

Add parameters for env, secrets, and files:
```python
def generate_infra_toml(
    # ... existing params ...
    env: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
    files: dict[str, str] | None = None,
) -> str:
```

Append new sections after existing content when non-empty.

**Extended `_format_dry_run_output()`:**

Show detected provisioning candidates:
```
Environment variables (provisioning):
  TELEGRAM_BOT_TOKEN → $TELEGRAM_BOT_TOKEN

Config files (provisioning):
  config.yaml ← config.yaml
```

**Tests:** `tests/unit/test_cli_init.py`
- [ ] `--check` on onboarded project reports undeclared env vars
- [ ] `--check` on onboarded project reports gitignored mounts
- [ ] `--check` suggests correct infra.toml additions
- [ ] `--check` on project with no gaps reports "all good"
- [ ] `--auto` includes secrets with `$VAR` default for detected env vars
- [ ] `--auto` includes files for gitignored mounts when source exists
- [ ] `--auto` skips gitignored mounts when source doesn't exist
- [ ] `generate_infra_toml()` with env/secrets/files appends correct sections
- [ ] `_format_dry_run_output()` shows provisioning candidates
- [ ] Interactive mode with env vars prompts for resolution type (mock typer.prompt)
- [ ] Existing interactive/auto/dry-run tests pass unchanged

**Acceptance Criteria:**
- [ ] `--check` reports all provisioning gaps
- [ ] Interactive mode prompts for each detected variable and mount
- [ ] `--auto` generates complete infra.toml with provisioning sections
- [ ] `--dry-run` shows provisioning candidates
- [ ] All tests pass
- [ ] Quality gates pass

---

## Task 2.3: E2E verification

**Type:** VALIDATION
**Estimated time:** 30 min

**Description:**
Validate discovery works on a real project with undeclared env vars and gitignored mounts.

**Test Steps:**

```bash
# Setup: create a project with env vars and gitignored config
mkdir -p /tmp/kinfra-disc-test && cd /tmp/kinfra-disc-test
git init && git commit --allow-empty -m "init"

cat > docker-compose.yml << 'EOF'
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - app-data:/app/data
    environment:
      - APP_SECRET=${APP_SECRET}
      - LOG_LEVEL=${LOG_LEVEL:-info}
      - CONFIG_PATH=/app/config.yaml

volumes:
  app-data:
EOF

cat > pyproject.toml << 'EOF'
[project]
name = "disc-test"
version = "0.1.0"
EOF

echo "config.yaml" > .gitignore
echo "setting: value" > config.yaml
git add -A && git commit -m "project setup"

# TEST 1: Fresh init --auto detects env vars and mounts
kinfra init --dry-run --auto
# Expected output includes:
#   - APP_SECRET detected as env var
#   - LOG_LEVEL detected as env var (with default: info)
#   - config.yaml detected as gitignored mount
#   - app-data NOT detected (it's a named volume, not a bind mount)

# TEST 2: Full auto init generates complete config
kinfra init --auto
cat .devops-ai/infra.toml
# Expected: includes [sandbox.secrets] with APP_SECRET = "$APP_SECRET"
# Expected: includes [sandbox.files] with "config.yaml" = "config.yaml"

# TEST 3: --check on already-onboarded project
# Add a new env var to compose that's not in infra.toml
# and re-run --check to verify gap detection

# Cleanup
rm -rf /tmp/kinfra-disc-test
```

**Also test against khealth:**

```bash
cd ~/Documents/dev/khealth
kinfra init --check
# Expected: detects TELEGRAM_BOT_TOKEN and config.yaml as gaps
# Expected: suggests correct infra.toml additions
```

**Success Criteria:**
- [ ] `--auto` detects env vars and generates `[sandbox.secrets]` section
- [ ] `--auto` detects gitignored mounts and generates `[sandbox.files]` section
- [ ] Named volumes are NOT flagged as mount candidates
- [ ] `--check` reports gaps on already-onboarded project
- [ ] Suggested infra.toml additions are correct and copy-pasteable
- [ ] All unit tests pass: `uv run pytest tests/unit`
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`

---

## Milestone 2 Completion Checklist

- [ ] All tasks complete and committed
- [ ] Unit tests pass: `uv run pytest tests/unit`
- [ ] E2E verification passes
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`
- [ ] No regressions in existing kinfra commands
- [ ] `kinfra init` produces complete infra.toml with provisioning sections for new projects
