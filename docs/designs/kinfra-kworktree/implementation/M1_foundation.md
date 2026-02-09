---
design: docs/designs/kinfra-kworktree/DESIGN.md
architecture: docs/designs/kinfra-kworktree/ARCHITECTURE.md
---

# Milestone 1: Foundation — CLI skeleton + config + worktrees

**Goal:** A developer can install kinfra, run `kinfra init` to generate config and parameterize their compose file, then use `kinfra spec` and `kinfra done` to create and remove worktrees.

**Branch:** `impl/kinfra-kworktree-M1`

---

## Task 1.1: Package foundation

**File(s):**
- `pyproject.toml` (create)
- `src/devops_ai/__init__.py` (create)
- `src/devops_ai/cli/__init__.py` (create)
- `src/devops_ai/cli/main.py` (create)
- `tests/__init__.py` (create)
- `tests/unit/__init__.py` (create)
- `tests/unit/test_smoke.py` (create)

**Type:** CODING
**Task Categories:** Configuration, Wiring/DI

**Description:**
Create the Python package structure for devops-ai's CLI. Set up `pyproject.toml` with the `kinfra` entry point, dependencies, and development tooling (pytest, ruff, mypy). Create the Typer app skeleton with `--help` working.

**Implementation Notes:**
- Entry point: `kinfra = "devops_ai.cli.main:main"`
- Dependencies: `typer[all]>=0.9`, `rich>=13`, `ruamel.yaml>=0.18`, `tomli>=2` (for Python < 3.11, use `tomllib` on 3.11+)
- Dev dependencies: `pytest>=8`, `ruff>=0.4`, `mypy>=1.10`
- Use `src/` layout (PEP 621)
- Typer app with placeholder commands that print "not yet implemented"
- Python requires `>=3.11` (tomllib is built-in)

**Tests:**
- Unit: `tests/unit/test_smoke.py`
  - `test_import`: `import devops_ai` succeeds
  - `test_cli_help`: `kinfra --help` returns 0 and contains "kinfra"

**Acceptance Criteria:**
- [ ] `uv tool install -e .` installs successfully
- [ ] `kinfra --help` shows all command stubs (init, spec, done, worktrees, impl, status, observability)
- [ ] `uv run pytest tests/unit` passes
- [ ] `uv run ruff check src/ tests/` passes
- [ ] `uv run mypy src/` passes

---

## Task 1.2: Config Loader

**File(s):**
- `src/devops_ai/config.py` (create)
- `tests/unit/test_config.py` (create)

**Type:** CODING
**Task Categories:** Configuration

**Description:**
Implement the config loader that parses `.devops-ai/infra.toml` and provides typed access to all configuration values. Implement `find_project_root()` which walks up the directory tree looking for `.devops-ai/`.

**Implementation Notes:**
- Use `tomllib` (Python 3.11+ stdlib) for TOML parsing
- `InfraConfig` dataclass with all fields from architecture doc
- `ServicePort` dataclass: `env_var: str`, `base_port: int`
- Parse `[sandbox.mounts]` code entries as Docker-style `host:container[:ro]` syntax
- `find_project_root()`: walk up from cwd, max 10 levels, looking for `.devops-ai/` directory
- If no `[sandbox]` section: `InfraConfig` with `has_sandbox = False`
- If no infra.toml at all: return `None` (callers decide behavior)
- Default prefix to project name if not specified
- Default health timeout to 60 if not specified

**Tests:**
- Unit: `tests/unit/test_config.py`
  - `test_parse_simple_config`: khealth-style 12-line config → correct InfraConfig
  - `test_parse_complex_config`: ktrdr-style 22-line config → correct InfraConfig
  - `test_parse_no_sandbox_section`: config with only `[project]` → has_sandbox=False
  - `test_parse_mount_syntax`: `"src/:/app/src"` → host="src/", container="/app/src", readonly=False
  - `test_parse_mount_readonly`: `"config/:/app/config:ro"` → readonly=True
  - `test_missing_required_field`: no `[project].name` → ValueError
  - `test_defaults`: missing prefix defaults to name, missing timeout defaults to 60
  - `test_find_project_root`: create temp dir structure, verify walk-up finds it
  - `test_find_project_root_not_found`: no `.devops-ai/` → returns None

**Acceptance Criteria:**
- [ ] Parses both simple (khealth) and complex (ktrdr-style) configs
- [ ] Docker-style mount syntax correctly parsed
- [ ] find_project_root walks up correctly
- [ ] Returns None when no config found (no error)
- [ ] All unit tests pass

---

## Task 1.3: Worktree Manager

**File(s):**
- `src/devops_ai/worktree.py` (create)
- `tests/unit/test_worktree.py` (create)

**Type:** CODING
**Task Categories:** Cross-Component

**Description:**
Implement git worktree operations: create spec worktrees, create impl worktrees, remove worktrees, list active worktrees, and check for dirty state. All git operations use subprocess calls to `git`.

**Implementation Notes:**
- Naming: `../<prefix>-spec-<feature>/` on branch `spec/<feature>`
- Naming: `../<prefix>-impl-<feature>-<milestone>/` on branch `impl/<feature>-<milestone>`
- Feature name validation: `^[a-zA-Z0-9_-]+$` (same as ktrdr)
- `create_spec_worktree()`: git fetch origin main, git worktree add, create `docs/designs/<feature>/` in worktree
- `create_impl_worktree()`: git fetch origin main, git worktree add
- `remove_worktree()`: `git worktree remove [--force]`
- `list_worktrees()`: parse `git worktree list --porcelain`, enrich with prefix matching to identify spec/impl
- `check_dirty()`: `git status --porcelain` + `git log @{u}..HEAD` for uncommitted/unpushed
- For impl without infra.toml: prefix falls back to parent directory name
- All git commands run with `cwd` set appropriately

**Tests:**
- Unit: `tests/unit/test_worktree.py`
  - `test_spec_worktree_path`: correct path computation
  - `test_impl_worktree_path`: correct path computation
  - `test_spec_branch_name`: `spec/<feature>`
  - `test_impl_branch_name`: `impl/<feature>-<milestone>`
  - `test_feature_name_validation`: valid and invalid names
  - `test_worktree_prefix_fallback`: no config → use directory name

- Integration (if git available):
  - `test_create_and_remove_spec_worktree`: full lifecycle in temp git repo
  - `test_dirty_check_uncommitted`: modified file detected
  - `test_dirty_check_unpushed`: unpushed commit detected
  - `test_dirty_check_clean`: clean worktree returns clean

**Acceptance Criteria:**
- [ ] Spec worktrees created with correct naming and branch
- [ ] Impl worktrees created with correct naming and branch
- [ ] Design directory created in spec worktrees
- [ ] Dirty check detects uncommitted changes and unpushed commits
- [ ] Feature name validation rejects invalid names
- [ ] Prefix fallback to directory name works when no config

---

## Task 1.4: CLI commands — spec, done, worktrees

**File(s):**
- `src/devops_ai/cli/spec.py` (create)
- `src/devops_ai/cli/done.py` (create)
- `src/devops_ai/cli/worktrees.py` (create)
- `src/devops_ai/cli/main.py` (modify — register commands)
- `tests/unit/test_cli_spec.py` (create)
- `tests/unit/test_cli_done.py` (create)

**Type:** CODING
**Task Categories:** API Endpoint (CLI), Cross-Component

**Description:**
Implement the three basic CLI commands. `spec` creates a design worktree. `done` removes a worktree (with dirty check and `--force` flag). `worktrees` lists all active worktrees. These commands use the Worktree Manager and Config Loader.

**Implementation Notes:**
- `kinfra spec <feature>`:
  - Load config (optional — works without it, falls back to dir name for prefix)
  - Validate feature name
  - Call `create_spec_worktree()`
  - Report: worktree path, branch name, design folder
- `kinfra done <name> [--force]`:
  - Find worktree by partial name match (search git worktree list)
  - If ambiguous match: error listing all matches
  - Check dirty (unless --force)
  - Call `remove_worktree()`
  - Report: worktree removed
  - (Sandbox cleanup added in M2)
- `kinfra worktrees`:
  - List worktrees from `git worktree list`
  - Identify spec/impl by prefix matching
  - Display Rich table with project, name, type, branch
  - (Slot info added in M2)
- Use `typer.echo()` for output and `rich.table.Table` for tabular display
- Use `typer.Exit(code=1)` for errors, not exceptions

**Tests:**
- Unit: `tests/unit/test_cli_spec.py`
  - `test_spec_invalid_feature_name`: exits with error
  - `test_spec_worktree_exists`: exits with error
- Unit: `tests/unit/test_cli_done.py`
  - `test_done_dirty_aborts`: exits with error when dirty (no --force)
  - `test_done_force_ignores_dirty`: proceeds with --force
  - `test_done_ambiguous_match`: exits with error listing matches

**Acceptance Criteria:**
- [ ] `kinfra spec my-feature` creates worktree and design dir
- [ ] `kinfra done my-feature` removes clean worktree
- [ ] `kinfra done my-feature` aborts on dirty worktree without --force
- [ ] `kinfra worktrees` lists all worktrees with type identification
- [ ] All commands work without infra.toml (fallback prefix)

---

## Task 1.5: CLI init — project inspection + config generation

**File(s):**
- `src/devops_ai/cli/init_cmd.py` (create)
- `src/devops_ai/cli/main.py` (modify — register init command)
- `tests/unit/test_cli_init.py` (create)

**Type:** CODING
**Task Categories:** Configuration, API Endpoint (CLI)

**Description:**
Implement the first half of `kinfra init`: project inspection (find compose files, parse services and ports, detect project name) and interactive config generation (prompts for name, prefix, health endpoint, code dirs, mount targets). Writes `.devops-ai/infra.toml`.

**Implementation Notes:**
- Find compose files: glob `docker-compose*.yml` and `compose*.yml`
- Parse compose YAML with `ruamel.yaml` to extract services and published ports
- Detect project name from: `.devops-ai/project.md` (look for `**Name:**`), `pyproject.toml` ([project].name), `package.json` (.name), directory name (fallback)
- Identify observability services by image name: `jaegertracing/*`, `prom/prometheus*`, `grafana/grafana*`
- Interactive prompts using `typer.prompt()` and `typer.confirm()`
- Present detected values as defaults (user presses Enter to accept)
- Write infra.toml using string formatting (TOML is simple enough)
- Create `.devops-ai/` directory if it doesn't exist
- Handle re-init: if infra.toml exists, show current config, ask "Update? (y/N)"
- Check Docker is running: `docker info` — warn if not (non-fatal for init)

**Tests:**
- Unit: `tests/unit/test_cli_init.py`
  - `test_detect_services_from_compose`: parse sample compose, extract services + ports
  - `test_identify_observability_services`: jaeger, prometheus, grafana detected by image
  - `test_detect_project_name_from_pyproject`: reads [project].name
  - `test_generate_infra_toml`: verify TOML output for khealth-style config
  - `test_reinit_detects_existing`: existing infra.toml triggers update prompt

**Acceptance Criteria:**
- [ ] Detects services and ports from docker-compose.yml
- [ ] Identifies observability services by image name
- [ ] Detects project name from multiple sources
- [ ] Interactive prompts with sensible defaults
- [ ] Generates valid infra.toml that Config Loader can parse
- [ ] Re-init on existing project offers update (doesn't silently overwrite)

---

## Task 1.6: CLI init — compose parameterization

**File(s):**
- `src/devops_ai/cli/init_cmd.py` (modify — add compose rewriting)
- `src/devops_ai/compose.py` (create — compose YAML rewriting logic)
- `tests/unit/test_compose.py` (create)

**Type:** CODING
**Task Categories:** Cross-Component

**Description:**
Implement compose file parameterization: replace hardcoded host ports with environment variables (using `${VAR:-default}` syntax), comment out observability services, and add header comments explaining kinfra usage. Uses `ruamel.yaml` for comment-preserving round-trip editing.

**Implementation Notes:**
- Use `ruamel.yaml` round-trip mode to preserve existing comments and formatting
- For each app service port mapping (e.g., `"8080:8080"`):
  - Replace with `"${KHEALTH_API_PORT:-8080}:8080"` (env var name from infra.toml `[sandbox.ports]` keys)
  - The env var name uses the project prefix + service role (generated during init prompts)
- For observability services:
  - Comment them out using YAML comments
  - Add explanation: "Commented out — kinfra provides shared observability. Uncomment for standalone use."
  - Handle `depends_on` references to removed services
- Add header comment block explaining the parameterization pattern
- Backup original compose to `docker-compose.yml.bak` before first modification
- If compose already has `${` patterns in ports: skip those (already parameterized)

**Tests:**
- Unit: `tests/unit/test_compose.py`
  - `test_parameterize_simple_ports`: `"8080:8080"` → `"${VAR:-8080}:8080"`
  - `test_parameterize_preserves_comments`: existing comments survive
  - `test_comment_out_observability`: jaeger service commented out
  - `test_add_header_comment`: header block present
  - `test_skip_already_parameterized`: `"${VAR:-8080}:8080"` left unchanged
  - `test_remove_depends_on_observability`: depends_on jaeger removed from app service
  - `test_backup_created`: original file backed up
  - `test_roundtrip_preserves_structure`: non-port YAML structure unchanged

**Acceptance Criteria:**
- [ ] Ports replaced with env var syntax, defaults preserved
- [ ] Observability services commented out with explanation
- [ ] Header comments added
- [ ] Existing comments and structure preserved (ruamel.yaml round-trip)
- [ ] Backup of original compose created
- [ ] Already-parameterized ports skipped
- [ ] Compose file works with `docker compose up` (defaults apply)

---

## Task 1.7: Install script update + M1 verification

**File(s):**
- `install.sh` (modify)
- `.devops-ai/project.md` (create — for devops-ai itself)

**Type:** MIXED
**Task Categories:** Configuration

**Description:**
Update the install script to include `uv tool install -e .` for the kinfra CLI alongside existing symlinks. Create `.devops-ai/project.md` for devops-ai itself. Run the full M1 E2E verification.

**Implementation Notes:**
- `install.sh` changes:
  - Check if `uv` is available; if not, warn and skip CLI install
  - Run `uv tool install -e .` from the devops-ai directory
  - Verify `kinfra --help` works after install
  - Keep existing symlink logic unchanged
- `.devops-ai/project.md` for devops-ai:
  - Name: devops-ai
  - Language: Python
  - Runner: uv
  - Unit tests: `uv run pytest tests/unit`
  - Quality: `uv run ruff check src/ tests/ && uv run mypy src/`
  - Integration: `uv run pytest tests/integration`
  - Design documents: `docs/designs/`

**Acceptance Criteria:**
- [ ] `./install.sh` installs CLI + symlinks without error
- [ ] `kinfra --help` works after fresh install
- [ ] `git pull && ./install.sh` updates CLI (editable install)

---

## Milestone 1 Verification

### E2E Test Scenario

**Purpose:** Verify kinfra can initialize a project and manage spec worktrees.
**Prerequisites:** git repo with a docker-compose.yml file

**Test Steps:**

```bash
# 1. Setup: create a test project
mkdir -p /tmp/test-kinfra-m1 && cd /tmp/test-kinfra-m1
git init && git commit --allow-empty -m "init"
cat > docker-compose.yml << 'EOF'
services:
  myapp:
    image: python:3.12-slim
    ports:
      - "8080:8080"
  jaeger:
    image: jaegertracing/jaeger:latest
    ports:
      - "16686:16686"
      - "4317:4317"
EOF
git add . && git commit -m "add compose"

# 2. Initialize
kinfra init
# Expected: prompts for name, prefix, health, code dirs
# Expected: .devops-ai/infra.toml created
# Expected: docker-compose.yml parameterized

# 3. Verify config
cat .devops-ai/infra.toml
# Expected: [project], [sandbox], [sandbox.ports] sections

# 4. Verify compose parameterization
grep '${' docker-compose.yml
# Expected: ${TEST_KINFRA_M1_MYAPP_PORT:-8080}:8080 (or similar)

# 5. Create spec worktree
kinfra spec my-feature
# Expected: ../test-kinfra-m1-spec-my-feature/ exists

# 6. List worktrees
kinfra worktrees
# Expected: table showing my-feature as spec type

# 7. Cleanup
kinfra done my-feature
# Expected: worktree removed

# 8. Teardown
cd / && rm -rf /tmp/test-kinfra-m1
```

**Success Criteria:**
- [ ] `kinfra init` generates valid infra.toml and parameterizes compose
- [ ] `kinfra spec` creates worktree with correct naming and branch
- [ ] `kinfra worktrees` lists the worktree
- [ ] `kinfra done` removes the worktree
- [ ] Compose file still works with `docker compose config` (valid YAML)

### Completion Checklist

- [ ] All tasks complete and committed
- [ ] Unit tests pass: `uv run pytest tests/unit`
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`
- [ ] E2E test passes (above)
- [ ] `kinfra --help` shows all commands
- [ ] install.sh works for fresh install
