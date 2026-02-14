# Sandbox Environment Provisioning: Design

**Target:** `devops-ai/docs/designs/sandbox-provisioning/DESIGN.md`
**Extends:** kinfra-kworktree design (sandbox slots, port isolation, override generation)

---

## Problem Statement

`kinfra impl` creates isolated worktrees with sandbox Docker environments, but the sandbox only handles **infrastructure concerns** (port isolation, OTEL injection, network attachment). Two categories of **application concerns** are missing:

1. **Secrets** — Compose services reference environment variables (`${TELEGRAM_BOT_TOKEN}`, `${ANTHROPIC_API_KEY}`) that aren't port-related. kinfra doesn't resolve or inject them. Containers fail to start or start broken.

2. **Config files** — Gitignored files (`config.yaml`, `.env`) don't exist in worktrees (git worktree only copies tracked files). Volume mounts like `./config.yaml:/app/config.yaml:ro` fail silently or crash the container.

Every project with Docker services hits this. The gap is that `kinfra impl` is advertised as a one-command sandbox setup, but the developer must still manually export secrets, copy config files, and debug missing-file errors. The value proposition breaks down at the first real project.

**Scope:** This design covers the **declaration format** (what projects specify in `infra.toml`) and the **behavior contract** (what kinfra does with those declarations). It does NOT cover implementation details inside kinfra's Python codebase.

---

## Goals

1. **A project declares everything its sandbox needs in `infra.toml`** — secrets, env vars, and config files alongside the existing port/mount/health declarations
2. **`kinfra impl` resolves and provisions everything before starting containers** — secrets from 1Password or host env, config files from the main repo
3. **Secrets never enter git** — resolved values live in the slot directory only, cleaned up on `kinfra done`
4. **Discovery is automated** — `kinfra init` detects undeclared env vars and gitignored volume mounts, proposes the right sections
5. **The format works for any project** — from a Telegram bot with one API key to a trading system with a dozen env vars and multiple config files
6. **Brownfield adoption is incremental** — existing onboarded projects (like khealth) can add these sections without re-running `kinfra init`

## Non-Goals

- **Not a vault or secrets manager** — kinfra resolves secrets at `impl` time; it doesn't store, rotate, or manage them
- **Not config file templating** — kinfra copies files, it doesn't do variable substitution inside them (apps should use env var overrides for per-environment values)
- **Not multi-environment** — this is dev sandbox provisioning, not staging/production config management
- **Not replacing 1Password** — `op://` references are a convenience; projects can use `$ENV_VAR` if they prefer a different secret source

---

## User Experience

### Scenario 1: Fresh project onboarding (greenfield)

```
$ cd ~/dev/my-new-project
$ kinfra init

Inspecting project...
  Found: docker-compose.yml (2 services: api, postgres)
  Found: Python project (pyproject.toml, name: my-project)

Services and ports:
  api: 8080 (API)
  postgres: 5432 (database)

? Health check endpoint? [/health]

Environment variables detected in compose (not ports):
  DATABASE_URL (api service)
  API_SECRET_KEY (api service)

? How should DATABASE_URL be provided?
  1. Literal value (safe for dev)
  2. Host environment variable ($DATABASE_URL)
  3. 1Password reference (op://vault/item/field)
  > 1: postgres://dev:dev@postgres:5432/mydb

? How should API_SECRET_KEY be provided?
  > 3: op://dev-vault/my-project/api-secret

Gitignored files mounted as volumes:
  .env → api service (./env:/app/.env:ro)

? Source for .env in sandboxes?
  1. Copy from main repo (.env — exists)
  2. Copy from template (.env.example — exists)
  > 1

Generated: .devops-ai/infra.toml
Updated:  docker-compose.yml (ports parameterized)

Ready! Try: kinfra impl my-feature/M1
```

### Scenario 2: Brownfield — adding provisioning to an existing project

khealth is already onboarded (has `infra.toml` with ports/health). Adding secrets and files:

```
$ kinfra init --check

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

The developer edits `infra.toml` manually (it's 2-4 lines). No re-init required.

### Scenario 3: `kinfra impl` with provisioning configured

```
$ kinfra impl ux-v1-1/M3

Created worktree: ../wellness-agent-impl-ux-v1-1-M3
  Branch: impl/ux-v1-1-M3
Provisioned files:
  config.yaml ← config.yaml ✓
Resolved secrets:
  TELEGRAM_BOT_TOKEN ← op://karl-wellness/telegram-token/password ✓
Sandbox:
  Slot: 1
  WELLNESS_AGENT_WELLNESS_AGENT_PORT: 8081
  Health: http://localhost:8081/api/v1/health ✓
```

One command. Everything works.

### Scenario 4: Secret resolution fails

```
$ kinfra impl ux-v1-1/M3

Created worktree: ../wellness-agent-impl-ux-v1-1-M3
  Branch: impl/ux-v1-1-M3
Provisioned files:
  config.yaml ← config.yaml ✓

✗ Secret resolution failed:
  TELEGRAM_BOT_TOKEN (op://karl-wellness/telegram-token/password)
  → 1Password not authenticated. Run: eval $(op signin)

Sandbox not started. To retry after fixing:
  kinfra sandbox start       (from worktree directory)
```

Worktree is preserved. Developer fixes auth, retries without recreating everything.

### Scenario 5: Config file source doesn't exist

```
$ kinfra impl ux-v1-1/M3

Created worktree: ../wellness-agent-impl-ux-v1-1-M3

✗ File provisioning failed:
  config.yaml — source not found at /Users/karl/dev/khealth/config.yaml
  Hint: Create it first: cp config.example.yaml config.yaml

Sandbox not started.
```

### Scenario 6: Evolution — project adds a new secret

Developer adds a new service that needs `STRIPE_API_KEY`. They:

1. Add `${STRIPE_API_KEY}` to docker-compose.yml
2. Add one line to infra.toml:
   ```toml
   STRIPE_API_KEY = "op://dev-vault/stripe/test-key"
   ```
3. Next `kinfra impl` resolves it automatically

No re-init. No migration. Just append a line.

### Scenario 7: Complex project (many services, many secrets)

```toml
[project]
name = "ktrdr"
prefix = "ktrdr"

[sandbox]
compose_file = "docker-compose.yml"

[sandbox.health]
endpoint = "/api/v1/health"
port_var = "KTRDR_API_PORT"
timeout = 120

[sandbox.ports]
KTRDR_API_PORT = 8000
KTRDR_DB_PORT = 5432
KTRDR_WORKER_PORT_1 = 5003

[sandbox.env]
APP_ENV = "sandbox"
KTRDR_LOG_LEVEL = "DEBUG"

[sandbox.secrets]
ANTHROPIC_API_KEY = "$ANTHROPIC_API_KEY"
KTRDR_DB_PASSWORD = "localdev"
KTRDR_AUTH_JWT_SECRET = "dev-secret-minimum-32-chars-long-enough"

[sandbox.files]
".env" = ".env.dev.example"
"config/local.yaml" = "config/local.yaml"
```

Same format, scales naturally.

---

## infra.toml Schema Additions

Three new optional sections extend the existing schema:

### `[sandbox.env]` — Non-secret environment variables

```toml
[sandbox.env]
APP_ENV = "sandbox"
LOG_LEVEL = "DEBUG"
FEATURE_FLAGS = "experimental"
```

Plain key-value pairs. Added to `.env.sandbox` alongside port variables and `COMPOSE_PROJECT_NAME`. For values that every sandbox needs but aren't sensitive.

### `[sandbox.secrets]` — Sensitive environment variables

```toml
[sandbox.secrets]
TELEGRAM_BOT_TOKEN = "op://karl-wellness/telegram-token/password"
ANTHROPIC_API_KEY = "$ANTHROPIC_API_KEY"
DB_PASSWORD = "localdev"
```

Each value is a **reference string** with three resolution types:

| Prefix | Resolution | When to use |
|--------|-----------|-------------|
| `op://` | 1Password CLI (`op read --no-newline <uri>`) | Production-grade secrets, API tokens |
| `$` | Host environment variable (`os.environ`) | Secrets already in shell profile, CI/CD |
| _(no prefix)_ | Literal value | Dev-only defaults (DB passwords, JWT secrets) |

**Security note:** Literal values in `infra.toml` are committed to git. Only use for non-sensitive dev defaults. Real secrets should use `op://` or `$` references.

### `[sandbox.files]` — Config files to provision

```toml
[sandbox.files]
"config.yaml" = "config.yaml"
".env" = ".env.example"
"certs/dev.pem" = "certs/dev.pem"
```

Each entry maps a **destination** (in the worktree) to a **source** (in the main repo working tree).

- **Source path** is relative to the project root, resolved from the **main repo** (not the worktree). This is critical because gitignored files only exist in the main working tree.
- **Destination path** is relative to the **worktree root**.
- Parent directories are created automatically.
- Files are copied (not symlinked) so the worktree can modify them independently.

---

## Resolution Behavior

### Order of operations in `kinfra impl`

```
1. Create worktree (git worktree add)
2. Provision files ([sandbox.files])         ← NEW
3. Resolve secrets ([sandbox.secrets])        ← NEW
4. Generate .env.sandbox (ports + [sandbox.env] + COMPOSE_PROJECT_NAME)  ← EXTENDED
5. Generate .env.secrets (resolved secrets)   ← NEW
6. Generate docker-compose.override.yml (mounts + OTEL + network)
7. docker compose up -d (with both env files)
8. Health gate
```

### Secret resolution (blocking, pre-startup)

All secrets must resolve before `docker compose up`. Partial resolution is not allowed — a sandbox with missing secrets is worse than no sandbox.

```
For each entry in [sandbox.secrets]:
  "op://..."  → subprocess: op read --no-newline <uri>
               → on failure: report "1Password not authenticated" or "item not found"
  "$VAR"      → os.environ["VAR"]
               → on failure: report "VAR not set in environment"
  "literal"   → use directly

Any failure → abort sandbox start, preserve worktree, report all failures at once
```

### File provisioning (blocking, pre-startup)

```
For each entry in [sandbox.files]:
  source = <main_repo_root> / <source_path>
  dest   = <worktree_path> / <dest_path>

  if source doesn't exist → error with hint
  mkdir -p dest.parent
  copy source → dest
```

### Where resolved secrets live

```
~/.devops-ai/slots/<project>-<N>/
  .env.sandbox          # ports + [sandbox.env] + COMPOSE_PROJECT_NAME  (existing)
  .env.secrets          # resolved [sandbox.secrets]                     (NEW)
  docker-compose.yml    # copy from worktree                            (existing)
  docker-compose.override.yml  # mounts + OTEL + network               (existing)
```

`.env.secrets` is:
- In the slot directory (never in the worktree, never in git)
- Passed to `docker compose up` via `--env-file`
- Deleted on `kinfra done` (entire slot dir removed)

Updated compose invocation:
```bash
docker compose \
  -f <compose> \
  -f <override> \
  --env-file .env.sandbox \
  --env-file .env.secrets \
  up -d
```

---

## Discovery: How `kinfra init` detects what's needed

### Detecting undeclared environment variables

`kinfra init` already parses the compose file for port mappings. Extend this:

1. Parse all `${VAR}` references in compose `environment:` sections
2. Subtract known variables: declared `[sandbox.ports]`, OTEL vars, `COMPOSE_PROJECT_NAME`
3. Remaining vars are candidates for `[sandbox.secrets]` or `[sandbox.env]`
4. For each: ask the user how it should be resolved (literal / $ENV / op://)

### Detecting gitignored volume mounts

1. Parse compose `volumes:` for bind mounts (`./path:/container/path`)
2. For each host path: check if it matches a `.gitignore` pattern
3. Gitignored mounts are candidates for `[sandbox.files]`
4. For each: check if the file exists in the project root (propose as source) or if an `.example` variant exists (propose as alternative source)

### Brownfield detection (`kinfra init --check`)

For already-onboarded projects, `--check` mode:
1. Loads existing `infra.toml`
2. Runs the same discovery (undeclared vars, gitignored mounts)
3. Reports gaps as suggestions (doesn't modify anything)
4. Developer adds lines to `infra.toml` manually

This is the same Phase 1 analyze behavior from `kinfra-onboard`, extended with env var and file detection.

---

## Key Decisions

### Decision 1: Secrets resolved at `impl` time, not deferred

**Choice:** kinfra resolves all secrets before starting containers. If resolution fails, the sandbox doesn't start.

**Alternatives:** Generate a placeholder file for the developer to fill in manually.

**Rationale:** The whole point of `kinfra impl` is one-command setup. Deferring secrets to a manual step defeats this. Failing fast with clear error messages (`run op signin`) is better than a half-started sandbox with cryptic container errors.

### Decision 2: Three resolution types (op://, $VAR, literal)

**Choice:** `op://` for 1Password, `$VAR` for host env, literal for dev defaults.

**Alternatives:** Support arbitrary secret managers (AWS Secrets Manager, HashiCorp Vault, etc.)

**Rationale:** These three cover ~95% of solo/small-team dev workflows. 1Password is the specific vault in use. `$VAR` handles CI/CD and alternative setups. Literals handle the "just works" dev case. Additional providers can be added later with a `provider://` URI scheme if needed.

### Decision 3: File copy from main repo, not template substitution

**Choice:** `[sandbox.files]` copies files as-is from the main repo working tree.

**Alternatives:** Template engine with `${VAR}` substitution inside config files.

**Rationale:** Template substitution requires kinfra to understand every config file format (YAML, TOML, INI, JSON, .env). This is fragile and project-specific. Instead, apps should use **environment variable overrides** for values that differ between environments — the compose override already injects OTEL env vars this way. Config files contain the "base" config; env vars provide per-sandbox overrides.

### Decision 4: Secrets in `.env.secrets`, not in `.env.sandbox`

**Choice:** Secrets get their own file, separate from ports/env vars.

**Alternatives:** Merge everything into one `.env.sandbox`.

**Rationale:** Separation of concerns. `.env.sandbox` contains only deterministic, non-sensitive values (ports, project name, LOG_LEVEL). `.env.secrets` contains resolved sensitive values. This makes it easier to reason about what's sensitive, and a future `kinfra sandbox refresh-secrets` command could regenerate just `.env.secrets` without touching ports.

### Decision 5: Source path resolved from main repo, not worktree

**Choice:** `[sandbox.files]` source paths resolve from the main repo's working directory.

**Alternatives:** Resolve from the worktree, or support both with a flag.

**Rationale:** The whole point of `[sandbox.files]` is to provision files that are gitignored — they only exist in the main working tree. Resolving from the worktree would defeat the purpose (the file wouldn't be there). If a developer wants a tracked file (like `.env.example`), it exists in both places — main repo resolution still works.

### Decision 6: Discovery integrated into existing `kinfra init` flow

**Choice:** Extend `kinfra init` to detect undeclared env vars and gitignored mounts.

**Alternatives:** Separate `kinfra provision init` subcommand.

**Rationale:** Secrets and config files are part of "what does this project need?" — the same question `kinfra init` already answers for ports and health checks. Splitting it into a separate command creates a two-step onboarding flow that's easy to forget. One command should set up everything.

---

## Error Handling

| Situation | Behavior |
|-----------|----------|
| `op read` fails (not authenticated) | Abort sandbox. Message: "1Password not authenticated. Run: `eval $(op signin)`" |
| `op read` fails (item not found) | Abort sandbox. Message: "Secret not found: op://vault/item/field. Check the reference in infra.toml." |
| `$VAR` not set in host env | Abort sandbox. Message: "Environment variable VAR not set. Export it or change to a different resolution type in infra.toml." |
| Source file not found | Abort sandbox. Message: "config.yaml not found at /path. Create it first: `cp config.example.yaml config.yaml`" |
| Multiple failures | Report all at once (don't stop at first). Developer can fix everything before retrying. |
| `op` CLI not installed | Abort sandbox. Message: "1Password CLI (op) not found. Install it or use $VAR references instead." |
| infra.toml has no [sandbox.secrets] | Skip secret resolution (existing behavior, no regression). |
| infra.toml has no [sandbox.files] | Skip file provisioning (existing behavior, no regression). |

### Recovery: `kinfra sandbox start`

When provisioning fails, the worktree is preserved. After fixing the issue (e.g., `op signin`), the developer runs `kinfra sandbox start` from the worktree directory. This re-runs provisioning + sandbox startup without recreating the worktree.

---

## Security Considerations

1. **Secrets never in git** — `.env.secrets` lives in `~/.devops-ai/slots/`, not the worktree
2. **Secrets never echoed** — `kinfra impl` output shows `✓` not the resolved value; `op read` uses `--no-newline` to prevent shell expansion issues
3. **Slot cleanup** — `kinfra done` deletes the entire slot dir including `.env.secrets`
4. **Literal secrets are visible in infra.toml** — this is by design for dev-only defaults; the developer chooses what's literal vs. referenced
5. **`$VAR` resolution** — reads from current shell environment; fails if unset (no silent empty string)
6. **No caching** — secrets are resolved fresh on each `kinfra impl`; no stale credential risk

---

## Impact on kinfra-onboard Skill

The kinfra-onboard skill's Phase 1 (Analyze) extends with two new checks:

1. **Undeclared env vars:** Parse compose `${VAR}` references, subtract known port/OTEL vars, report remaining as "needs [sandbox.secrets] or [sandbox.env]"
2. **Gitignored volume mounts:** Parse compose bind mounts, check .gitignore, report as "needs [sandbox.files]"

Phase 2 (Propose) presents these as additional `infra.toml` lines.
Phase 3 (Execute) appends them to `infra.toml` if the user approves.

This makes onboarding complete — one run of `/kinfra-onboard` produces a fully provisioned sandbox config.

---

## Open Questions

1. **`kinfra sandbox start` for retry** — Should this be a new subcommand, or should `kinfra impl` detect an existing worktree without a running sandbox and offer to start it?

2. **Secret rotation** — If a secret changes in 1Password, existing sandboxes have the old value in `.env.secrets`. Should there be a `kinfra sandbox refresh` that re-resolves secrets without recreating the sandbox?

3. **Per-service secrets** — Current design injects all secrets as env vars available to all compose services. Should there be a way to scope secrets to specific services? (Probably not needed for dev sandboxes, but worth noting.)

4. **Config file overrides** — If a developer wants to tweak the provisioned config.yaml in their worktree, should `kinfra impl` skip copying if the destination already exists? (Useful for re-runs, but could mask stale configs.)
