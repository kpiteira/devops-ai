---
design: ../DESIGN.md
architecture: ../ARCHITECTURE.md
---

# Milestone 2: kinfra-onboard skill

**Goal:** A developer runs `/kinfra-onboard` in any project and gets an intelligent, phased onboarding experience with safety checks, OTEL rewiring, and a clean git commit.

---

## Task 2.1: Create kinfra-onboard SKILL.md

**File(s):** `skills/kinfra-onboard/SKILL.md`
**Type:** CODING
**Estimated time:** 2-3 hours

**Description:**
Write the skill document that instructs Claude Code how to run the phased onboarding workflow. This is the intelligence layer that reads a project, assesses safety, calls `kinfra init`, adapts app-level config, and verifies results.

**Implementation Notes:**

The skill follows the same YAML frontmatter pattern as other skills:
```yaml
---
name: kinfra-onboard
description: Onboard a project to the kinfra sandbox and shared observability ecosystem.
metadata:
  version: "0.1.0"
---
```

**Structure the skill in these sections:**

1. **Invocation** — `/kinfra-onboard [--check]`

2. **Prerequisites** — kinfra CLI must be installed (`which kinfra`), project must be a git repo

3. **Phase 1: Analyze** — Read-only assessment:
   - Read `.devops-ai/project.md` (project name, existing config)
   - Read `.devops-ai/infra.toml` (already onboarded?)
   - Find and read `docker-compose*.yml` / `compose*.yml`
   - Scan for OTEL config: search for `otel`, `4317`, `jaeger` in config files (YAML, .env, etc.) — NOT in Python source
   - Run `git status --porcelain` to check for dirty state
   - **Report findings** in structured format (project name, services, obs services, OTEL config location, git state, onboarding status)
   - **Blockers:** If already onboarded, report and offer re-run. If dirty git, warn and pause. If no compose, offer worktree-only setup.
   - **--check mode:** Stop here, report only.

4. **Phase 2: Propose** — Preview changes:
   - Run `kinfra init --dry-run --auto` (add `--health-endpoint <detected>` if healthcheck found in compose)
   - Identify OTEL config changes needed: old endpoint → `http://localhost:44317`
   - Identify project.md changes: add/update Infrastructure section
   - Identify docs/skills referencing old local obs endpoints
   - **Present full plan** to user: kinfra dry-run output + skill's own planned changes
   - **Wait for user approval** before proceeding

5. **Phase 3: Execute** — Make changes:
   - Run `kinfra init --auto` (add `--health-endpoint` if detected)
   - Edit OTEL config files: change endpoint to `http://localhost:44317`
   - Edit `.devops-ai/project.md`: add Infrastructure section with:
     ```
     ## Infrastructure
     - **Start:** kinfra impl <feature>/<milestone>
     - **Stop:** kinfra done <name>
     - **Observability:** kinfra observability up
     - **Status:** kinfra status
     ```
   - Edit docs/skills referencing old Jaeger ports (e.g. `14686` → `46686`, `14317` → `44317`)
   - **Track all changed files** for the commit

6. **Phase 4: Verify & Commit** — Validate and commit:
   - Verify `.devops-ai/infra.toml` exists and is valid TOML
   - Verify compose file is valid YAML (read and parse)
   - Verify no remaining references to old obs endpoints in config files
   - `git add <tracked files>` (explicit list, never `-A`)
   - `git commit -m "chore: onboard to kinfra sandbox and shared observability"`
   - Report summary of all changes

7. **Error Handling** section:
   - kinfra not found → "Run install.sh in devops-ai"
   - kinfra init fails → Show error, discuss with user
   - Verification fails → Full rollback (restore .bak, delete infra.toml, git checkout edited files)
   - OTEL config not found → Report to user, skip OTEL rewiring (app may not have observability)
   - OTEL config in Python source only → Surface to user, recommend adding config-based override

8. **Shared Observability Reference** section:
   - Shared stack ports: Jaeger UI `46686`, Grafana `43000`, Prometheus `49090`, OTLP gRPC `44317`
   - OTEL endpoint for app config: `http://localhost:44317`
   - In sandbox: env var `OTEL_EXPORTER_OTLP_ENDPOINT=http://devops-ai-jaeger:4317` overrides config
   - Start stack: `kinfra observability up`

**Tests:**
- Manual validation (Task 2.2)

**Acceptance Criteria:**
- [ ] SKILL.md follows frontmatter + sections pattern from other skills
- [ ] All 4 phases documented with clear instructions
- [ ] --check mode documented
- [ ] Error handling section covers all cases from SCENARIOS.md
- [ ] Shared observability reference section included
- [ ] Skill is discoverable after `install.sh` run (symlinked to `~/.claude/skills/`)

---

## Task 2.2: E2E validation on khealth

**Type:** VALIDATION
**Estimated time:** 30 min

**Description:**
Run `/kinfra-onboard` on the khealth project (`../khealth`) to validate the full 4-phase flow works end-to-end.

**Prerequisites:**
- M1 complete (kinfra init --dry-run --auto working)
- khealth has clean git state
- Skill installed (run `install.sh` or symlink manually)

**Test Steps:**

1. **Prep:** Ensure khealth is on a clean branch
```bash
cd /Users/karl/Documents/dev/khealth
git status  # should be clean
```

2. **--check mode first:** Run `/kinfra-onboard --check` in khealth
   - Verify: Reports project name (wellness-agent), compose services, Jaeger obs service, OTEL config at config.yaml, git clean, not onboarded
   - Verify: No files changed

3. **Full onboarding:** Run `/kinfra-onboard` in khealth
   - Phase 1: Verify analysis report matches --check output
   - Phase 2: Verify proposal shows kinfra dry-run output + OTEL rewiring plan. Approve.
   - Phase 3: Verify execution:
     - `.devops-ai/infra.toml` created
     - `docker-compose.yml` parameterized (port 8080 has `${...:-8080}`)
     - `docker-compose.yml` has Jaeger commented out
     - `config.yaml` OTEL endpoint → `http://localhost:44317`
     - `.devops-ai/project.md` has Infrastructure section
   - Phase 4: Verify commit created with all changed files

4. **Post-onboarding checks:**
```bash
# infra.toml is valid
cat .devops-ai/infra.toml

# compose still parses
python3 -c "from ruamel.yaml import YAML; YAML().load(open('docker-compose.yml'))"

# OTEL points to shared stack
grep 44317 config.yaml

# project.md has Infrastructure
grep -A5 "## Infrastructure" .devops-ai/project.md

# git log shows commit
git log --oneline -1
```

5. **Cleanup:** Revert the onboarding commit if this is just validation
```bash
git revert HEAD --no-edit  # or reset if preferred
```

**Success Criteria:**
- [ ] --check mode reports correctly without changing files
- [ ] Full onboarding completes all 4 phases
- [ ] infra.toml is valid and contains correct project name and ports
- [ ] Compose is parameterized with Jaeger commented out
- [ ] OTEL endpoint updated to shared stack
- [ ] project.md has Infrastructure section
- [ ] Single git commit contains all changes
- [ ] No regressions in kinfra unit tests: `cd /Users/karl/Documents/dev/devops-ai && uv run pytest tests/unit`

---

## Milestone 2 Completion Checklist

- [ ] SKILL.md created and follows conventions
- [ ] install.sh picks up new skill automatically
- [ ] E2E validation on khealth passes
- [ ] kinfra unit tests still pass: `uv run pytest tests/unit`
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`
