# Sandbox Environment Provisioning: Architecture

**Companion to:** `DESIGN.md` (same directory)
**Extends:** kinfra codebase at `src/devops_ai/`

---

## Component Overview

```
                        ┌─────────────────┐
                        │  kinfra impl    │
                        │  (cli/impl.py)  │
                        └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │             │
              ┌─────▼─────┐ ┌───▼────┐ ┌─────▼──────┐
              │  Secret    │ │  File  │ │  Env File  │
              │  Resolver  │ │ Prov.  │ │  Generator │
              │  (NEW)     │ │ (NEW)  │ │ (EXTENDED) │
              └─────┬──────┘ └───┬────┘ └─────┬──────┘
                    │            │             │
              ┌─────▼──────┐ ┌──▼───┐  ┌──────▼──────┐
              │.env.secrets│ │files │  │.env.sandbox │
              │(slot dir)  │ │(wt)  │  │(slot dir)   │
              └────────────┘ └──────┘  └─────────────┘
                    │                         │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼──────────┐
                    │  docker compose up   │
                    │  --env-file sandbox  │
                    │  --env-file secrets  │
                    └──────────────────────┘


                    ┌─────────────────────┐
                    │  kinfra init        │
                    │  (cli/init_cmd.py)  │
                    └────────┬────────────┘
                             │
                ┌────────────┼────────────┐
                │            │            │
          ┌─────▼──────┐ ┌──▼─────┐ ┌────▼─────┐
          │  Env Var    │ │ Volume │ │  Existing│
          │  Detector   │ │ Mount  │ │  Port/   │
          │  (NEW)      │ │ Det.   │ │  Health  │
          └─────┬──────┘ │ (NEW)  │ │  Det.    │
                │        └──┬─────┘ └────┬─────┘
                └───────────┼────────────┘
                            │
                    ┌───────▼────────┐
                    │  infra.toml    │
                    │  generation    │
                    └────────────────┘
```

---

## New Module: `src/devops_ai/provision.py`

All provisioning logic lives in one new module. Pure functions — no CLI, no prompts.

### Secret Resolution

```python
def resolve_secret(ref: str) -> str:
    """Resolve a single secret reference to its value.

    Raises SecretResolutionError with a user-actionable message.
    """

def resolve_all_secrets(
    secrets: dict[str, str],
) -> tuple[dict[str, str], list[SecretResolutionError]]:
    """Resolve all secrets. Returns (resolved, errors).

    Always attempts ALL secrets — does not stop at first failure.
    """

class SecretResolutionError(Exception):
    """Secret resolution failure with actionable guidance.

    Attributes:
        var_name: The env var name (e.g., TELEGRAM_BOT_TOKEN)
        ref: The reference string (e.g., op://vault/item/field)
        message: User-facing error with fix instructions
    """
```

Resolution dispatch:

| Ref prefix | Handler | Error message |
|------------|---------|---------------|
| `op://` | `subprocess.run(["op", "read", "--no-newline", ref])` | `TELEGRAM_BOT_TOKEN: 1Password not authenticated. Run: eval $(op signin)` or `TELEGRAM_BOT_TOKEN: Secret not found in 1Password: op://vault/item. Check the reference in infra.toml.` |
| `$` | `os.environ[ref[1:]]` | `TELEGRAM_BOT_TOKEN: Environment variable TELEGRAM_BOT_TOKEN not set. Export it or change to a different source in infra.toml.` |
| _(no prefix)_ | Return as-is | _(never fails)_ |
| _(op CLI missing)_ | `shutil.which("op") is None` | `TELEGRAM_BOT_TOKEN: 1Password CLI (op) not found. Install: brew install 1password-cli — or use $VAR references instead.` |

### File Provisioning

```python
def provision_files(
    files: dict[str, str],
    main_repo_root: Path,
    worktree_path: Path,
) -> tuple[list[str], list[FileProvisionError]]:
    """Copy config files from main repo to worktree.

    Returns (provisioned_files, errors).
    Always attempts ALL files — does not stop at first failure.
    """

class FileProvisionError(Exception):
    """File provisioning failure with hint.

    Attributes:
        dest: Destination path (relative)
        source: Source path (relative)
        message: User-facing error with fix instructions
    """
```

Error messages:

| Situation | Message |
|-----------|---------|
| Source not found | `config.yaml: Source not found at /Users/karl/dev/khealth/config.yaml` + hint if `.example` variant exists: `Hint: cp config.yaml.example config.yaml` |
| Source is directory | `config.yaml: Source is a directory, not a file. Check the path in infra.toml [sandbox.files].` |

### Secrets Env File Generation

```python
def generate_secrets_file(
    resolved_secrets: dict[str, str],
    slot_dir: Path,
) -> Path:
    """Write .env.secrets to slot directory. Returns path."""
```

Output format (same as .env.sandbox):
```
TELEGRAM_BOT_TOKEN=the-resolved-value
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Modified Components

### `config.py` — Extended InfraConfig

```python
@dataclass
class InfraConfig:
    # ... existing fields unchanged ...

    # NEW: Provisioning config
    env: dict[str, str] = field(default_factory=dict)        # [sandbox.env]
    secrets: dict[str, str] = field(default_factory=dict)    # [sandbox.secrets]
    files: dict[str, str] = field(default_factory=dict)      # [sandbox.files]
```

Parsing in `load_config()`:
```python
# After existing OTEL parsing
env = sandbox.get("env", {})
secrets = sandbox.get("secrets", {})
files = sandbox.get("files", {})
```

All three are `dict[str, str]` — keys are env var names (or destination paths for files), values are reference strings (or source paths).

### `sandbox.py` — Extended env file + compose command

**`generate_env_file()`** — append `[sandbox.env]` entries after port vars:

```python
# After port lines
for key, value in sorted(config.env.items()):
    lines.append(f"{key}={value}")
```

**`_compose_cmd()`** — support multiple env files:

```python
def _compose_cmd(
    compose_file: str | Path,
    override_file: str | Path,
    env_files: list[str | Path],  # was: single env_file
    action: list[str],
) -> list[str]:
    cmd = ["docker", "compose", "-f", str(compose_file), "-f", str(override_file)]
    for ef in env_files:
        cmd.extend(["--env-file", str(ef)])
    cmd.extend(action)
    return cmd
```

**`start_sandbox()` / `stop_sandbox()`** — pass list of env files, including `.env.secrets` when it exists.

### `cli/impl.py` — Provisioning step in `_setup_sandbox()`

Insert between `generate_override` and `start_sandbox`:

```python
# Generate files (existing)
generate_env_file(config, slot_info, slot_dir)
generate_override(config, slot_info, wt_path, repo_root, slot_dir)

# NEW: Provision files and secrets
if config.files:
    provisioned, file_errors = provision_files(config.files, repo_root, wt_path)
    # report provisioned files in output

if config.secrets:
    resolved, secret_errors = resolve_all_secrets(config.secrets)
    # report resolved secrets in output (✓ not values)

all_errors = file_errors + secret_errors
if all_errors:
    # Cleanup: release slot, remove slot dir, keep worktree
    release_slot(registry, slot_id)
    remove_slot_dir(slot_dir)
    return 1, _format_provision_failure(all_errors, wt_path)

if resolved:
    generate_secrets_file(resolved, slot_dir)

# Start sandbox (existing, but now with .env.secrets)
start_sandbox(config, slot_info, wt_path)
```

### Error output format

When provisioning fails, the output must be actionable:

```
Created worktree: ../wellness-agent-impl-ux-v1-1-M3
  Branch: impl/ux-v1-1-M3

Provisioned files:
  config.yaml <- config.yaml ✓

✗ Provisioning failed:

  TELEGRAM_BOT_TOKEN (op://karl-wellness/telegram-token/password)
    1Password not authenticated. Run: eval $(op signin)

  STRIPE_API_KEY ($STRIPE_API_KEY)
    Environment variable STRIPE_API_KEY not set.
    Export it or change to a different source in infra.toml.

Sandbox not started. After fixing, run:
  cd ../wellness-agent-impl-ux-v1-1-M3 && kinfra sandbox start
```

The last line is the key UX — the developer knows exactly what to do next.

---

## New Subcommand: `kinfra sandbox start`

Recovery command for when provisioning fails but the worktree is preserved.

### Behavior

1. Detect current directory is a kinfra worktree (check registry for matching worktree_path)
2. Look up slot info from registry
3. Re-run provisioning: resolve secrets, copy files
4. Generate .env.secrets (overwrite if exists)
5. Start sandbox containers

### Interface

```python
# cli/sandbox_cmd.py
def sandbox_start_command(
    repo_root: Path | None = None,
) -> tuple[int, str]:
    """Start sandbox for existing worktree. Returns (exit_code, message).

    Finds slot from registry by matching cwd to worktree_path.
    Re-runs provisioning before starting containers.
    """
```

### Where it finds context

The worktree path is the current directory. The slot info is in the registry (matched by `worktree_path`). The config comes from `load_config()` on the worktree's own `.devops-ai/infra.toml` (which is tracked in git and present in all worktrees). The main repo root is derived from the worktree's git configuration.

### CLI wiring

```
kinfra sandbox start   — re-provision + start containers
kinfra sandbox stop    — stop containers (alias for compose down)
kinfra sandbox status  — existing status command (may move here later)
```

`sandbox` becomes a Typer sub-app, similar to `observability`.

---

## Discovery: Extended `detect_project()` in `init_cmd.py`

### Env Var Detection

```python
def detect_env_vars(
    compose_content: str,
    known_vars: set[str],
) -> list[EnvVarCandidate]:
    """Find ${VAR} references in compose, subtract known vars.

    known_vars: port vars + OTEL vars + COMPOSE_PROJECT_NAME
    Returns candidates for [sandbox.secrets] or [sandbox.env].
    """
```

Parse `${VAR}` and `${VAR:-default}` patterns from the raw compose text (not YAML-parsed, since we need to find references in all contexts — environment, command, labels, etc.).

Regex: `\$\{([A-Z_][A-Z0-9_]*)(?::-[^}]*)?\}`

### Gitignored Volume Mount Detection

```python
def detect_gitignored_mounts(
    compose_content: str,
    project_root: Path,
) -> list[FileMountCandidate]:
    """Find bind mounts to gitignored files.

    Uses `git check-ignore` for correct gitignore interpretation.
    Returns candidates for [sandbox.files].
    """
```

Steps:
1. Parse compose YAML for bind mounts (`./path:/container/path` format)
2. For each host path, run `git check-ignore -q <path>`
3. If ignored (exit 0): candidate for `[sandbox.files]`
4. Check if source exists in project root (propose as source)
5. Check if `.example` variant exists (propose as alternative)

### Extended InitPlan

```python
@dataclass
class InitPlan:
    # ... existing fields ...

    # NEW: Provisioning candidates
    env_var_candidates: list[EnvVarCandidate] = field(default_factory=list)
    file_mount_candidates: list[FileMountCandidate] = field(default_factory=list)


@dataclass
class EnvVarCandidate:
    name: str
    services: list[str]     # which services reference it
    default: str | None     # from ${VAR:-default}, if present


@dataclass
class FileMountCandidate:
    host_path: str          # relative to project root
    container_path: str     # inside container
    service: str            # which service mounts it
    source_exists: bool     # does the file exist in main repo?
    example_exists: bool    # does a .example variant exist?
    example_path: str | None
```

### Extended `generate_infra_toml()`

New parameters for env, secrets, and files sections:

```python
def generate_infra_toml(
    # ... existing params ...
    env: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
    files: dict[str, str] | None = None,
) -> str:
```

Appends new sections after existing content:

```toml
[sandbox.env]
APP_ENV = "sandbox"

[sandbox.secrets]
TELEGRAM_BOT_TOKEN = "$TELEGRAM_BOT_TOKEN"   # or op://vault/item/field

[sandbox.files]
"config.yaml" = "config.yaml"
```

---

## Data Flow: `kinfra impl` with provisioning

```
kinfra impl feat/M1
  │
  ├── parse feature/milestone
  ├── load_config()  ──────────────────────────── reads infra.toml
  │     └── InfraConfig with .env, .secrets, .files
  │
  ├── create_impl_worktree()
  │
  ├── _setup_sandbox()
  │     ├── allocate_slot()
  │     ├── create_slot_dir()
  │     ├── claim_slot()
  │     │
  │     ├── generate_env_file()  ──────────────── ports + [sandbox.env] → .env.sandbox
  │     ├── generate_override()  ──────────────── networks + OTEL + mounts → override.yml
  │     │
  │     ├── provision_files()  ────────────────── [sandbox.files]: main repo → worktree
  │     │     └── errors? → report all, suggest `kinfra sandbox start`
  │     │
  │     ├── resolve_all_secrets()  ────────────── [sandbox.secrets]: op:// / $VAR / literal
  │     │     └── errors? → report all, suggest `kinfra sandbox start`
  │     │
  │     ├── generate_secrets_file()  ──────────── resolved secrets → .env.secrets
  │     │
  │     ├── start_sandbox()  ──────────────────── compose up with both env files
  │     └── run_health_gate()
  │
  └── report (worktree, slot, ports, provisioned files, resolved secrets ✓)
```

## Data Flow: `kinfra sandbox start` (recovery)

```
kinfra sandbox start
  │
  ├── find slot from registry by cwd == worktree_path
  ├── load_config() from worktree's .devops-ai/infra.toml
  ├── find main repo root (git rev-parse for main worktree)
  │
  ├── provision_files()  ──── re-copy from main repo
  ├── resolve_all_secrets()  ── re-resolve (fresh, no cache)
  │     └── errors? → report all, same format as impl
  │
  ├── generate_secrets_file()  ── overwrite .env.secrets in slot dir
  │
  ├── start_sandbox()
  └── run_health_gate()
```

---

## State: What Lives Where

| Artifact | Location | Lifecycle | Sensitive? |
|----------|----------|-----------|------------|
| `infra.toml` | `.devops-ai/infra.toml` (project root, tracked) | Permanent | No (references only, not values) |
| `.env.sandbox` | `~/.devops-ai/slots/<project>-<N>/` | Created by impl, deleted by done | No |
| `.env.secrets` | `~/.devops-ai/slots/<project>-<N>/` | Created by impl, deleted by done | **Yes** |
| Provisioned files | `<worktree>/` (e.g., `config.yaml`) | Created by impl, deleted with worktree | Maybe |
| Compose copy | `~/.devops-ai/slots/<project>-<N>/` | Created by impl, deleted by done | No |
| Override | `~/.devops-ai/slots/<project>-<N>/` | Created by impl, deleted by done | No |

---

## Milestones

### M1: Provisioning Pipeline

The smallest slice that makes khealth's sandbox work end-to-end.

**Delivers:**
- `[sandbox.secrets]`, `[sandbox.files]`, `[sandbox.env]` parsing in `load_config()`
- Secret resolver with op://, $VAR, literal support
- File provisioner (copy from main repo to worktree)
- `.env.secrets` generation
- Extended `.env.sandbox` with `[sandbox.env]` entries
- Extended `docker compose` invocation with multiple `--env-file`
- `kinfra sandbox start` subcommand for recovery
- Clear, actionable error messages on failure

**E2E test:** Manually add `[sandbox.secrets]` and `[sandbox.files]` to khealth's `infra.toml`. Run `kinfra impl`. Verify container starts with TELEGRAM_BOT_TOKEN resolved and config.yaml mounted. Health check passes.

### M2: Discovery

Extend `kinfra init` to detect what needs provisioning.

**Delivers:**
- Env var detection (parse `${VAR}` references, subtract known vars)
- Gitignored volume mount detection (`git check-ignore`)
- `--check` mode reports gaps with suggested `infra.toml` lines
- Interactive prompts for resolution type (literal / $VAR / op://)
- `--auto` mode generates complete infra.toml with provisioning sections
- Extended `generate_infra_toml()` with new sections

**E2E test:** Run `kinfra init --check` on a project with undeclared env vars and gitignored mounts. Verify it detects both and suggests correct infra.toml additions.
