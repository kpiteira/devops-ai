---
design: docs/designs/sandbox-provisioning/DESIGN.md
architecture: docs/designs/sandbox-provisioning/ARCHITECTURE.md
---

# Milestone 1: Provisioning Pipeline

**Goal:** `kinfra impl` resolves secrets, copies config files, and generates `.env.secrets` before starting containers. When provisioning fails, clear error messages guide the developer to fix the issue and retry via `kinfra sandbox start`.

---

## Task 1.1: Extend InfraConfig with provisioning sections

**File(s):** `src/devops_ai/config.py`
**Type:** CODING
**Estimated time:** 1 hour

**Description:**
Add three new optional fields to `InfraConfig` and parse them from `infra.toml`. These correspond to `[sandbox.env]`, `[sandbox.secrets]`, and `[sandbox.files]` — all `dict[str, str]`, all optional, all default to empty dict.

**Implementation Notes:**

Add to `InfraConfig` dataclass:
```python
env: dict[str, str] = field(default_factory=dict)        # [sandbox.env]
secrets: dict[str, str] = field(default_factory=dict)    # [sandbox.secrets]
files: dict[str, str] = field(default_factory=dict)      # [sandbox.files]
```

In `load_config()`, after the existing OTEL parsing block:
```python
env = sandbox.get("env", {})
secrets = sandbox.get("secrets", {})
files = sandbox.get("files", {})
```

Pass them through to the `InfraConfig(...)` constructor.

TOML types map directly — `[sandbox.env]` is a table of string key-value pairs, which `tomllib` returns as `dict[str, str]`. Same for `[sandbox.secrets]` and `[sandbox.files]`.

**Tests:** `tests/unit/test_config.py`
- [ ] `load_config()` parses `[sandbox.env]` entries into `config.env`
- [ ] `load_config()` parses `[sandbox.secrets]` entries into `config.secrets`
- [ ] `load_config()` parses `[sandbox.files]` entries into `config.files`
- [ ] Missing sections default to empty dicts (no regression on existing configs)
- [ ] All three sections together in one infra.toml parse correctly

**Acceptance Criteria:**
- [ ] Existing tests pass unchanged (backward compatible)
- [ ] New fields accessible on loaded config
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`

---

## Task 1.2: Secret resolver and file provisioner

**File(s):** `src/devops_ai/provision.py` (NEW)
**Type:** CODING
**Estimated time:** 2 hours

**Description:**
Create a new module with pure functions for resolving secrets and copying config files. All error reporting is collected (not fail-fast) so the developer can fix everything in one pass.

**Implementation Notes:**

**Secret resolution:**

```python
class SecretResolutionError(Exception):
    def __init__(self, var_name: str, ref: str, message: str): ...

def resolve_secret(var_name: str, ref: str) -> str:
    """Resolve one secret reference. Raises SecretResolutionError."""

def resolve_all_secrets(
    secrets: dict[str, str],
) -> tuple[dict[str, str], list[SecretResolutionError]]:
    """Resolve all secrets. Returns (resolved_dict, errors).
    Attempts ALL — does not stop at first failure."""
```

Resolution dispatch by prefix:
- `op://...` → `subprocess.run(["op", "read", "--no-newline", ref], capture_output=True, text=True, timeout=30)`. Check `shutil.which("op")` first. On failure, parse stderr for "not signed in" vs "item not found" to give specific guidance.
- `$VAR` → `os.environ[ref[1:]]`. KeyError → `SecretResolutionError`.
- No prefix → literal, return as-is (never fails).

Error messages must be user-actionable (per architecture doc):
- `TELEGRAM_BOT_TOKEN: 1Password not authenticated. Run: eval $(op signin)`
- `TELEGRAM_BOT_TOKEN: Secret not found in 1Password: op://vault/item. Check the reference in infra.toml.`
- `TELEGRAM_BOT_TOKEN: 1Password CLI (op) not found. Install: brew install 1password-cli — or use $VAR references instead.`
- `TELEGRAM_BOT_TOKEN: Environment variable TELEGRAM_BOT_TOKEN not set. Export it or change to a different source in infra.toml.`

**File provisioning:**

```python
class FileProvisionError(Exception):
    def __init__(self, dest: str, source: str, message: str): ...

def provision_files(
    files: dict[str, str],
    main_repo_root: Path,
    worktree_path: Path,
) -> tuple[list[str], list[FileProvisionError]]:
    """Copy files from main repo to worktree. Returns (provisioned, errors).
    Attempts ALL — does not stop at first failure."""
```

For each entry: `dest` (key) is relative to worktree, `source` (value) is relative to main repo root. Create parent dirs with `mkdir(parents=True, exist_ok=True)`. Copy with `shutil.copy2`.

Check for `.example` variant when source is missing — include in error hint.

**Secrets env file:**

```python
def generate_secrets_file(
    resolved_secrets: dict[str, str],
    slot_dir: Path,
) -> Path:
    """Write .env.secrets to slot dir. Returns path."""
```

Same format as `.env.sandbox` — one `KEY=VALUE` per line.

**Tests:** `tests/unit/test_provision.py` (NEW)
- [ ] `resolve_secret()` with literal value returns it as-is
- [ ] `resolve_secret()` with `$VAR` reads from environment
- [ ] `resolve_secret()` with `$VAR` raises `SecretResolutionError` when unset
- [ ] `resolve_secret()` with `op://` when `op` not installed raises with install hint
- [ ] `resolve_secret()` with `op://` when `op` fails raises with appropriate message
- [ ] `resolve_secret()` with `op://` success returns resolved value (mock subprocess)
- [ ] `resolve_all_secrets()` collects ALL errors, not just first
- [ ] `resolve_all_secrets()` returns resolved dict for successes alongside errors
- [ ] `provision_files()` copies file from main repo to worktree
- [ ] `provision_files()` creates parent directories
- [ ] `provision_files()` error when source doesn't exist, with hint if `.example` exists
- [ ] `provision_files()` collects ALL errors
- [ ] `generate_secrets_file()` writes KEY=VALUE format to slot dir

**Acceptance Criteria:**
- [ ] All resolution types work (op://, $VAR, literal)
- [ ] Errors are collected, not fail-fast
- [ ] Error messages include actionable fix instructions
- [ ] File provisioning handles missing parents
- [ ] Quality gates pass

---

## Task 1.3: Integration — provisioning in impl + sandbox start

**File(s):** `src/devops_ai/sandbox.py`, `src/devops_ai/cli/impl.py`, `src/devops_ai/cli/sandbox_cmd.py` (NEW), `src/devops_ai/cli/main.py`
**Type:** CODING
**Estimated time:** 2-3 hours

**Description:**
Wire provisioning into the `kinfra impl` flow and add the `kinfra sandbox start` recovery command. This is the integration task — connecting the pure functions from task 1.2 to the CLI.

**Implementation Notes:**

**1. Extend `_compose_cmd()` for multiple env files** (`sandbox.py`):

Change signature from single `env_file` to `env_files: list[str | Path]`. Update all callers (`start_sandbox`, `stop_sandbox`). When `.env.secrets` exists in slot dir, include it in the list.

```python
def _compose_cmd(
    compose_file: str | Path,
    override_file: str | Path,
    env_files: list[str | Path],
    action: list[str],
) -> list[str]:
    cmd = ["docker", "compose", "-f", str(compose_file), "-f", str(override_file)]
    for ef in env_files:
        cmd.extend(["--env-file", str(ef)])
    cmd.extend(action)
    return cmd
```

**2. Extend `generate_env_file()`** (`sandbox.py`):

After writing port vars, append `[sandbox.env]` entries:
```python
for key, value in sorted(config.env.items()):
    lines.append(f"{key}={value}")
```

**3. Build `_env_files_for_slot()` helper** (`sandbox.py`):

Returns the list of env files for a slot dir — always `.env.sandbox`, plus `.env.secrets` if it exists:
```python
def _env_files_for_slot(slot_dir: Path) -> list[Path]:
    files = [slot_dir / ".env.sandbox"]
    secrets = slot_dir / ".env.secrets"
    if secrets.exists():
        files.append(secrets)
    return files
```

Update `start_sandbox()` and `stop_sandbox()` to use this.

**4. Insert provisioning in `_setup_sandbox()`** (`cli/impl.py`):

Between `generate_override()` and `start_sandbox()`:

```python
# Provision files
file_errors: list[FileProvisionError] = []
provisioned_files: list[str] = []
if config.files:
    provisioned_files, file_errors = provision_files(
        config.files, repo_root, wt_path
    )

# Resolve secrets
secret_errors: list[SecretResolutionError] = []
resolved_secrets: dict[str, str] = {}
if config.secrets:
    resolved_secrets, secret_errors = resolve_all_secrets(config.secrets)

# Abort on any errors
all_errors = file_errors + secret_errors
if all_errors:
    release_slot(registry, slot_id)
    remove_slot_dir(slot_dir)
    return 1, _format_provision_failure(all_errors, wt_path)

# Write secrets file
if resolved_secrets:
    generate_secrets_file(resolved_secrets, slot_dir)
```

**5. Error message formatting** (`cli/impl.py`):

```python
def _format_provision_failure(
    errors: list[SecretResolutionError | FileProvisionError],
    wt_path: Path,
) -> str:
```

Output format (per architecture doc):
```
Created worktree: ../wellness-agent-impl-ux-v1-1-M3
  Branch: impl/ux-v1-1-M3

✗ Provisioning failed:

  TELEGRAM_BOT_TOKEN (op://karl-wellness/telegram-token/password)
    1Password not authenticated. Run: eval $(op signin)

Sandbox not started. After fixing, run:
  cd ../wellness-agent-impl-ux-v1-1-M3 && kinfra sandbox start
```

**6. Success output** — extend the report in `_setup_sandbox()`:

```
Provisioned files:
  config.yaml <- config.yaml ✓
Resolved secrets:
  TELEGRAM_BOT_TOKEN <- op://... ✓
```

Never print resolved secret values — only `✓`.

**7. `kinfra sandbox start` subcommand** (`cli/sandbox_cmd.py` NEW):

```python
def sandbox_start_command(
    worktree_path: Path | None = None,
) -> tuple[int, str]:
```

Steps:
1. `worktree_path` defaults to `Path.cwd()`
2. Load registry, find slot by `worktree_path` match
3. If no slot found: error "Not a kinfra worktree, or sandbox not allocated"
4. Load config from worktree's `.devops-ai/infra.toml`
5. Find main repo root via `git rev-parse --path-format=absolute --git-common-dir` then parent
6. Re-run provisioning (files + secrets) — same logic as impl
7. Generate `.env.secrets` (overwrite if exists)
8. Start sandbox + health gate
9. Report success

Wire into `main.py` as Typer sub-app:
```python
sandbox_app = typer.Typer()
sandbox_app.command(name="start")(sandbox_start)
app.add_typer(sandbox_app, name="sandbox")
```

**Tests:** `tests/unit/test_impl.py`, `tests/unit/test_sandbox.py`, `tests/unit/test_sandbox_cmd.py` (NEW)
- [ ] `_compose_cmd()` builds correct command with multiple env files
- [ ] `generate_env_file()` includes `[sandbox.env]` entries after ports
- [ ] `_env_files_for_slot()` returns both files when .env.secrets exists
- [ ] `_env_files_for_slot()` returns only .env.sandbox when no secrets
- [ ] `_setup_sandbox()` calls provisioning when config has secrets/files
- [ ] `_setup_sandbox()` skips provisioning when config has no secrets/files (no regression)
- [ ] `_setup_sandbox()` aborts and cleans up when provisioning fails
- [ ] `_format_provision_failure()` produces actionable error with `kinfra sandbox start` hint
- [ ] `sandbox_start_command()` finds slot from registry by worktree path
- [ ] `sandbox_start_command()` errors when not in a kinfra worktree
- [ ] `sandbox_start_command()` re-runs provisioning before starting

**Acceptance Criteria:**
- [ ] `kinfra impl` provisions files and secrets when configured
- [ ] `kinfra impl` aborts cleanly on provisioning failure with actionable error
- [ ] `kinfra sandbox start` recovers from failed provisioning
- [ ] Existing impl flow unchanged when no provisioning config
- [ ] All tests pass
- [ ] Quality gates pass

---

## Task 1.4: E2E verification

**Type:** VALIDATION
**Estimated time:** 30 min

**Description:**
Validate the full provisioning pipeline against a real project. Test both the happy path (everything resolves) and the error path (clear error messages + recovery).

**Test Steps:**

```bash
# Setup: create a test project with secrets and config files
mkdir -p /tmp/kinfra-prov-test && cd /tmp/kinfra-prov-test
git init && git commit --allow-empty -m "init"

cat > docker-compose.yml << 'EOF'
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - APP_SECRET=${APP_SECRET}
      - CONFIG_PATH=/app/config.yaml
EOF

cat > pyproject.toml << 'EOF'
[project]
name = "prov-test"
version = "0.1.0"
EOF

echo "config.yaml" > .gitignore
echo "setting: value" > config.yaml
git add -A && git commit -m "project setup"

# Onboard with kinfra init --auto
kinfra init --auto

# Manually add provisioning sections to infra.toml
cat >> .devops-ai/infra.toml << 'EOF'

[sandbox.env]
APP_ENV = "sandbox"

[sandbox.secrets]
APP_SECRET = "$APP_SECRET"

[sandbox.files]
"config.yaml" = "config.yaml"
EOF

# Create a milestone file
mkdir -p docs/designs/test-feat/implementation
echo "# M1" > docs/designs/test-feat/implementation/M1_test.md
git add -A && git commit -m "add provisioning config"

# TEST 1: Error path — secret not set
kinfra impl test-feat/M1
# Expected: provisioning fails, error mentions APP_SECRET not set,
# suggests "kinfra sandbox start"

# TEST 2: Happy path — set the secret and recover
export APP_SECRET="test-secret-value"
cd ../prov-test-impl-test-feat-M1
kinfra sandbox start
# Expected: provisioning succeeds, sandbox starts

# Verify:
# - config.yaml exists in worktree
# - .env.secrets exists in slot dir with APP_SECRET=test-secret-value
# - Container has APP_SECRET and APP_ENV env vars

# TEST 3: Verify no-provisioning regression
# (run kinfra impl on a project without [sandbox.secrets]/[sandbox.files])

# Cleanup
kinfra done test-feat-M1
rm -rf /tmp/kinfra-prov-test
```

**Also test against khealth (if available):**

```bash
cd ~/Documents/dev/khealth

# Add provisioning config
cat >> .devops-ai/infra.toml << 'EOF'

[sandbox.secrets]
TELEGRAM_BOT_TOKEN = "$TELEGRAM_BOT_TOKEN"

[sandbox.files]
"config.yaml" = "config.yaml"
EOF

# Ensure TELEGRAM_BOT_TOKEN is in environment
# Run kinfra impl on a feature
# Verify: container starts, health check passes, config.yaml in worktree
```

**Success Criteria:**
- [ ] Provisioning failure produces clear, actionable error message
- [ ] Error message includes `kinfra sandbox start` command
- [ ] `kinfra sandbox start` successfully recovers after fixing the issue
- [ ] Happy path: files copied, secrets resolved, container starts
- [ ] Secret values never printed to terminal
- [ ] Existing projects without provisioning config work unchanged
- [ ] All unit tests pass: `uv run pytest tests/unit`
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`

---

## Milestone 1 Completion Checklist

- [ ] All tasks complete and committed
- [ ] Unit tests pass: `uv run pytest tests/unit`
- [ ] E2E verification passes
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`
- [ ] No regressions in existing kinfra commands (`impl`, `done`, `init`, `status`)
