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
# kinfra CLI must be installed
which kinfra || echo "ERROR: kinfra not found. Run install.sh in devops-ai."

# Must be in a git repository
git rev-parse --git-dir || echo "ERROR: Not a git repository."
```

If either check fails, stop and report the error with remediation instructions.

---

## Phase 1: Analyze

**Goal:** Read-only assessment of the project's current state. No files are changed.

### Steps

1. **Read project configuration:**
   - Read `.devops-ai/project.md` — extract project name if present
   - Read `.devops-ai/infra.toml` — if exists, project is already onboarded

2. **Find and read compose file:**
   - Search for `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, `compose.yaml`
   - If found: parse services, ports, health checks, depends_on relationships
   - If not found: note this — project can use worktree-only setup

3. **Identify observability services:**
   - Match service images against known patterns:
     - `jaegertracing/*` or `jaeger` → Jaeger
     - `prom/prometheus` or `prometheus` → Prometheus
     - `grafana/grafana` or `grafana` → Grafana
   - These will be commented out (replaced by shared stack)

4. **Scan for OTEL configuration:**
   - Search config files (YAML, TOML, .env) for: `otel`, `4317`, `jaeger`, `otlp`
   - Do NOT search Python source files — only config files
   - Note the file path and current endpoint value

5. **Check git state:**
   ```bash
   git status --porcelain
   ```
   - Clean → proceed
   - Dirty → will warn in report

### Report

Present findings in this format:

```
## Project Analysis

- **Project:** <name> (from project.md or pyproject.toml or directory name)
- **Git state:** Clean | Dirty (N uncommitted changes)
- **Compose:** <filename> (<N> services)
  - <service>: port <port>, health check at <path>
  - <service>: ports <ports> (observability — shared stack replaces this)
- **OTEL config:** <file> → endpoint: "<current value>"
  | No OTEL config found in config files
- **kinfra status:** Not onboarded | Already onboarded (infra.toml exists)
```

### Blockers

Check for these conditions and handle accordingly:

| Condition | Action |
|-----------|--------|
| Already onboarded (infra.toml exists) | Report current state. Ask: "Re-run onboarding? This will update compose and config." |
| Dirty git state | Warn: "Uncommitted changes detected. Recommend committing or stashing first." Pause for user decision. |
| No compose file found | Report: "No docker-compose file found. kinfra requires Docker Compose for sandbox management. You can still use kinfra for worktree management." Offer to create minimal infra.toml with `has_sandbox = false`. |
| Unrecognized observability service | Surface to user: "I see a '<service>' service that might be observability but I'm not sure. Should I treat it as an app service (keep) or observability (comment out)?" |

### --check mode

If `--check` flag was passed: **stop here**. Report the analysis and exit. Do not proceed to Phase 2.

---

## Phase 2: Propose

**Goal:** Preview all changes and get user approval before modifying anything.

### Steps

1. **Run kinfra dry-run:**
   ```bash
   kinfra init --dry-run --auto
   ```
   If a health endpoint was detected in Phase 1:
   ```bash
   kinfra init --dry-run --auto --health-endpoint <detected-path>
   ```
   Capture and display the output.

2. **Identify OTEL config changes:**
   - If OTEL config was found in Phase 1: plan to change endpoint to `http://localhost:44317`
   - If OTEL config is only in Python source (no config file mechanism): surface to user — recommend adding config-based override rather than editing source

3. **Identify project.md changes:**
   - Plan to add/update the `## Infrastructure` section with kinfra commands

4. **Identify docs/skills changes:**
   - Search for references to old local observability ports (e.g., `14686`, `14317`, `16686`, `4317` in non-compose config files)
   - Plan to update these to shared stack ports (`46686`, `44317`)

### Present Plan

Show the full change plan to the user:

```
## Proposed Changes

**kinfra init will:**
<dry-run output>

**I will also:**
- Update <config-file>: OTEL endpoint → http://localhost:44317
- Update .devops-ai/project.md: Add Infrastructure section
- Update <docs/skills files> referencing local Jaeger ports (if any)

Proceed? (yes/no)
```

**Wait for explicit user approval before proceeding to Phase 3.**

If user says no: abort cleanly. No changes have been made.

### Error Handling

| Situation | Action |
|-----------|--------|
| `kinfra init --dry-run` fails | Show the error output. Discuss with user — do not proceed. |
| kinfra not found | Error: "kinfra CLI not found. Run `install.sh` in the devops-ai repository." |

---

## Phase 3: Execute

**Goal:** Make all changes. Track every file modified for the commit.

### Track Changed Files

Maintain a list of all files changed during this phase. Initialize it empty at the start.

### Steps

1. **Run kinfra init:**
   ```bash
   kinfra init --auto
   ```
   If health endpoint was detected:
   ```bash
   kinfra init --auto --health-endpoint <detected-path>
   ```
   This creates:
   - `.devops-ai/infra.toml` → add to changed files
   - `docker-compose.yml` (rewritten) → add to changed files
   - `docker-compose.yml.bak` (backup) → do NOT add to changed files

2. **Update OTEL config:**
   - If OTEL config file was identified in Phase 1:
     - Read the file
     - Change the OTEL endpoint to `http://localhost:44317`
     - Write the file back
     - Add to changed files
   - If no OTEL config found: skip this step (report skipped)

3. **Update project.md:**
   - Read `.devops-ai/project.md`
   - If `## Infrastructure` section exists: replace it
   - If not: add it after `## Testing` (or at the end)
   - Content:
     ```markdown
     ## Infrastructure

     - **Start:** kinfra impl <feature>/<milestone>
     - **Stop:** kinfra done <name>
     - **Observability:** kinfra observability up
     - **Status:** kinfra status
     ```
   - Add to changed files

4. **Update docs/skills with old obs references:**
   - If references to old local Jaeger ports were found in Phase 2:
     - Update each file (e.g., `14686` → `46686`, `14317` → `44317`)
     - Add each to changed files
   - If none found: skip

### Output

Report what was changed:

```
## Changes Made

Files changed:
- .devops-ai/infra.toml (created by kinfra init)
- docker-compose.yml (rewritten by kinfra init)
- <config-file> (OTEL endpoint updated)
- .devops-ai/project.md (Infrastructure section added)
```

---

## Phase 4: Verify & Commit

**Goal:** Validate all changes are consistent and correct, then commit.

### Verification Checks

1. **infra.toml is valid:**
   ```bash
   python3 -c "import tomllib; tomllib.load(open('.devops-ai/infra.toml', 'rb'))"
   ```
   Must succeed with no errors.

2. **Compose file is valid YAML:**
   ```bash
   python3 -c "from ruamel.yaml import YAML; YAML().load(open('docker-compose.yml'))"
   ```
   Must parse without errors.

3. **No remaining old obs references in config files:**
   - Search config files (not Python source) for old local Jaeger endpoints
   - Any remaining references should be flagged

### On Verification Success

Create a single commit with all tracked files:

```bash
git add <each tracked file explicitly>
git commit -m "chore: onboard to kinfra sandbox and shared observability"
```

Never use `git add -A` — only stage files tracked during Phase 3.

Report the commit and summary of all changes.

### On Verification Failure

**Full rollback:**

1. Restore compose from backup:
   ```bash
   cp docker-compose.yml.bak docker-compose.yml
   ```
2. Delete generated infra.toml:
   ```bash
   rm .devops-ai/infra.toml
   ```
3. Restore any skill-edited files:
   ```bash
   git checkout <each edited file>
   ```
4. Report what failed and why. Discuss with user before retrying.

---

## Error Handling

| Situation | Phase | Action |
|-----------|-------|--------|
| kinfra CLI not found | Any | "Run `install.sh` in the devops-ai repository to install kinfra." |
| kinfra init fails | 3 | Show error output. Discuss with user — do not proceed. |
| Compose doesn't parse after changes | 4 | Full rollback (restore .bak, delete infra.toml, git checkout edited files). |
| infra.toml invalid after creation | 4 | Full rollback. Report the issue. |
| OTEL config not found in config files | 1 | Report: "No OTEL configuration found in config files. App may not have observability, or it may be hardcoded in source." Skip OTEL rewiring. |
| OTEL config only in Python source | 2 | Surface to user: "OTEL endpoint is configured in Python source (<file>), not a config file. Recommend adding a config-based override (env var or config file) rather than editing source directly." |
| User denies proposal | 2 | Abort cleanly. No changes made. |
| Dirty git state | 1 | Warn user. Pause for decision (commit, stash, or proceed anyway). |
| Already onboarded | 1 | Report current state. Offer re-run. If user re-runs, `kinfra init --auto` handles existing config gracefully. |

---

## Shared Observability Reference

The shared observability stack runs on dedicated ports to avoid conflicts:

| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| Jaeger UI | 46686 | 16686 | Distributed traces |
| Grafana | 43000 | 3000 | Dashboards |
| Prometheus | 49090 | 9090 | Metrics |
| OTLP gRPC | 44317 | 4317 | Trace ingestion |

**For app config files (local dev):** `http://localhost:44317`

**For sandbox containers (Docker network):** env var `OTEL_EXPORTER_OTLP_ENDPOINT=http://devops-ai-jaeger:4317` is set automatically by the sandbox override generator. Apps should prefer the env var over config file values when available.

**Start the shared stack:** `kinfra observability up`

---

## Example Session

```
User: /kinfra-onboard

## Project Analysis

- **Project:** wellness-agent (from .devops-ai/project.md)
- **Git state:** Clean
- **Compose:** docker-compose.yml (2 services)
  - wellness-agent: port 8080, health check at /api/v1/health
  - jaeger: ports 14686, 14317 (observability — shared stack replaces this)
- **OTEL config:** config.yaml → endpoint: "http://jaeger:4317"
- **kinfra status:** Not onboarded (no infra.toml)

No blockers found. Proceeding to Phase 2.

---

## Proposed Changes

**kinfra init will:**
  Project: wellness-agent
  Compose: docker-compose.yml
  - Parameterize port 8080
  - Comment out service: jaeger
  - Generate .devops-ai/infra.toml

**I will also:**
- Update config.yaml: OTEL endpoint → http://localhost:44317
- Update .devops-ai/project.md: Add Infrastructure section

Proceed?

User: yes

---

## Changes Made

- .devops-ai/infra.toml (created)
- docker-compose.yml (rewritten)
- config.yaml (OTEL endpoint updated)
- .devops-ai/project.md (Infrastructure section added)

---

## Verification

- infra.toml: valid TOML
- docker-compose.yml: valid YAML
- OTEL references: all pointing to shared stack

Committed: "chore: onboard to kinfra sandbox and shared observability"
```
