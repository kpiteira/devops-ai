---
name: kinfra-onboard
description: Onboard a project to the kinfra sandbox and shared observability ecosystem.
metadata:
  version: "0.1.0"
---

# kinfra-onboard — Project Onboarding

Onboard any project to the kinfra ecosystem: sandbox isolation via Docker Compose, shared observability (Jaeger/Grafana/Prometheus), and worktree management.

**Usage:** `/kinfra-onboard [--check]`

- Default: Full 4-phase onboarding (Analyze, Propose, Execute, Verify)
- `--check`: Phase 1 only — report project status without making changes

---

## Prerequisites

Before starting, verify:

```bash
which kinfra || echo "ERROR: kinfra not found. Run install.sh in devops-ai."
git rev-parse --git-dir || echo "ERROR: Not a git repository."
```

If either check fails, stop and report the error with remediation instructions.

---

## Phase 1: Analyze

Read-only assessment of the project's current state. No files are changed.

1. **Read project configuration:**
   - Read `.devops-ai/project.md` — extract project name if present
   - Read `.devops-ai/infra.toml` — if exists, project is already onboarded

2. **Find and read compose file:**
   - Search for `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, `compose.yaml`
   - If found: parse services, ports, health checks, depends_on relationships
   - If not found: note this — project can use worktree-only setup

3. **Identify observability services:**
   - Match service images: `jaegertracing/*` → Jaeger, `prom/prometheus` → Prometheus, `grafana/grafana` → Grafana
   - These will be commented out (replaced by shared stack)

4. **Scan for OTEL configuration:**
   - Search config files (YAML, TOML, .env) for: `otel`, `4317`, `jaeger`, `otlp`
   - Do not search Python source files — only config files
   - Note the file path and current endpoint value

5. **Check git state:** Clean → proceed. Dirty → warn in report.

### Report

Present findings:

```
## Project Analysis

- **Project:** <name>
- **Git state:** Clean | Dirty (N uncommitted changes)
- **Compose:** <filename> (<N> services)
  - <service>: port <port>, health check at <path>
  - <service>: ports <ports> (observability — shared stack replaces this)
- **OTEL config:** <file> → endpoint: "<current value>"
- **kinfra status:** Not onboarded | Already onboarded (infra.toml exists)
```

### Blockers

| Condition | Action |
|-----------|--------|
| Already onboarded | Report current state. Offer re-run. |
| Dirty git state | Warn. Pause for user decision (commit, stash, or proceed). |
| No compose file | Note worktree-only setup. Offer minimal infra.toml with `has_sandbox = false`. |
| Unrecognized observability service | Ask user whether to treat as app (keep) or observability (comment out). |

If `--check` flag was passed: stop here. Report and exit.

---

## Phase 2: Propose

Preview all changes and get user approval before modifying anything.

1. **Run kinfra dry-run:**
   ```bash
   kinfra init --dry-run --auto [--health-endpoint <detected-path>]
   ```
   Capture and display the output.

2. **Identify OTEL config changes:**
   - If found: plan to change endpoint to `http://localhost:44317`
   - If only in Python source: recommend config-based override rather than source editing

3. **Plan project.md update:** Add/update `## Infrastructure` section with kinfra commands.

4. **Plan docs/skills updates:** Search for old local Jaeger ports (`14686`, `14317`, `16686`, `4317`) in non-compose config files. Plan to update to shared stack ports.

### Present Plan

Show the full change plan. Wait for explicit user approval before proceeding to Phase 3. If user declines, abort cleanly — no changes have been made.

---

## Phase 3: Execute

Make all changes. Track every file modified for the commit.

1. **Run kinfra init:**
   ```bash
   kinfra init --auto [--health-endpoint <detected-path>]
   ```
   Creates `.devops-ai/infra.toml` and rewrites the compose file (`.bak` backup created automatically).

2. **Update OTEL config:** If identified in Phase 1, change endpoint to `http://localhost:44317`. If not found, skip.

3. **Update project.md:** Add or replace `## Infrastructure` section:
   ```markdown
   ## Infrastructure

   - **Start:** kinfra impl <feature>/<milestone>
   - **Stop:** kinfra done <name>
   - **Observability:** kinfra observability up
   - **Status:** kinfra status
   ```

4. **Update docs/skills with old obs references:** Change old local Jaeger ports to shared stack ports. If none found, skip.

Report all files changed.

---

## Phase 4: Verify & Commit

Validate all changes are consistent, then commit.

### Verification

1. **infra.toml is valid:**
   ```bash
   python3 -c "import tomllib; tomllib.load(open('.devops-ai/infra.toml', 'rb'))"
   ```

2. **Compose file is valid YAML:**
   ```bash
   python3 -c "from ruamel.yaml import YAML; YAML().load(open('docker-compose.yml'))"
   ```

3. **No remaining old obs references** in config files.

### On Success

Commit tracked files only (not `git add -A`):
```bash
git add <each tracked file explicitly>
git commit -m "chore: onboard to kinfra sandbox and shared observability"
```

### On Failure — Full Rollback

1. Restore compose from backup: `cp docker-compose.yml.bak docker-compose.yml`
2. Delete generated infra.toml: `rm .devops-ai/infra.toml`
3. Restore edited files: `git checkout <each edited file>`
4. Report what failed and why. Discuss before retrying.

---

## Error Handling

| Situation | Action |
|-----------|--------|
| kinfra CLI not found | "Run `install.sh` in devops-ai." |
| kinfra init fails | Show error output. Discuss — do not proceed. |
| Compose doesn't parse after changes | Full rollback. |
| OTEL config not in config files | Report and skip OTEL rewiring. |
| OTEL config only in Python source | Recommend config-based override. |

---

## Shared Observability Reference

| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| Jaeger UI | 46686 | 16686 | Distributed traces |
| Grafana | 43000 | 3000 | Dashboards |
| Prometheus | 49090 | 9090 | Metrics |
| OTLP gRPC | 44317 | 4317 | Trace ingestion |

**For app config files (local dev):** `http://localhost:44317`

**For sandbox containers:** env var `OTEL_EXPORTER_OTLP_ENDPOINT=http://devops-ai-jaeger:4317` is set automatically by the sandbox override generator. Apps should prefer the env var over config file values when available.

**Start the shared stack:** `kinfra observability up`
