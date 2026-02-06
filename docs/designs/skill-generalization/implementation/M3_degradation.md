---
design: docs/designs/skill-generalization/DESIGN.md
architecture: docs/designs/skill-generalization/ARCHITECTURE.md
---

# Milestone 3: Graceful Degradation + Config Generation

**Branch:** `feature/devops-ai-M3-degradation`
**Project Root:** `~/Documents/dev/devops-ai/`
**Goal:** Skills work without config and can help create one.

> **All file paths in this plan are relative to the devops-ai repo.**
> This plan is executed from ktrdr (which has the k* commands) but all
> files are created and modified in `~/Documents/dev/devops-ai/`.

**Builds on:** M2 (skills must exist to add degradation behavior)

---

## E2E Validation

### Test Scenario

```bash
# 1. Verify no-config language exists in all skills
grep -l "does NOT exist\|file does not exist\|not found" skills/*/SKILL.md | wc -l  # should be 5

# 2. Verify config generation guidance exists
grep -l "create.*config\|generate.*config\|offer to create" skills/*/SKILL.md | wc -l  # at least 1

# 3. Verify project inspection references
grep -l "pyproject.toml\|package.json\|Makefile\|go.mod" skills/*/SKILL.md | wc -l  # at least 1

# 4. Verify partial-config handling
grep -l "not configured\|Not configured\|skip.*section" skills/*/SKILL.md | wc -l  # should be 5
```

**Success Criteria:**
- [ ] All 5 skills handle missing config gracefully (ask for essentials)
- [ ] At least one skill offers to generate config from project inspection
- [ ] Partial config is handled (use what's there, ask for missing essentials)
- [ ] Skills note what sections were skipped due to missing config

---

## Task 3.1: Add No-Config Behavior to All Skills

**File(s):** All 5 `skills/*/SKILL.md` (modify)
**Type:** CODING
**Estimated time:** 2 hours
**Architectural Pattern:** Graceful Degradation

**Description:**
Enhance the Configuration Loading preamble in all 5 skills to handle the case where `.devops-ai/project.md` doesn't exist. Currently the preamble says to "ask for essentials and offer to create one" — this task makes that instruction specific and actionable.

**What to change:**
Update the Configuration Loading section in each skill to include explicit no-config behavior:

For skills that need **minimal config** (kdesign, kdesign-validate):
```
If .devops-ai/project.md does NOT exist:
- Ask: "Where do you store design documents?" (default: docs/designs/)
- Ask: "What's the project name?"
- Proceed with answers. Suggest creating config for future sessions.
```

For skills that need **more config** (ktask, kmilestone, kdesign-impl-plan):
```
If .devops-ai/project.md does NOT exist:
- Ask: "What command runs your unit tests?"
- Ask: "What command runs quality/lint checks?"
- Ask: "Where do you store design documents?" (default: docs/designs/)
- Note: Infrastructure and E2E features require config. These sections will be skipped.
- Suggest creating config for future sessions.
```

**Implementation Notes:**
- The questions should be specific to what each skill actually needs (see Skill-to-Config Value Mapping in SCENARIOS.md)
- Don't ask for values the skill doesn't use — kdesign doesn't need test commands
- Keep the no-config path lightweight — 3-4 questions max, then proceed
- The "offer to create config" is just a suggestion at this point — Task 3.2 adds the actual generation

**Acceptance Criteria:**
- [ ] All 5 skills have explicit no-config behavior in their Configuration Loading section
- [ ] Questions are specific to each skill's actual config needs
- [ ] No skill asks more than 4 questions in the no-config path
- [ ] All skills suggest creating config for future sessions
- [ ] Infrastructure/E2E sections are noted as skipped when no config

---

## Task 3.2: Add Config Generation Capability

**File(s):** All 5 `skills/*/SKILL.md` (modify — add shared guidance)
**Type:** CODING
**Estimated time:** 2 hours
**Architectural Pattern:** Graceful Degradation

**Description:**
Add project inspection and config generation guidance so skills can help users create their `.devops-ai/project.md` from project context.

**What to add:**
After the no-config questions in the Configuration Loading section, add guidance for generating a config file:

```
If the user wants to create a config file:
1. Inspect the project root for:
   - pyproject.toml → Python project (extract test commands, project name)
   - package.json → Node/TypeScript project (extract scripts.test, name)
   - Makefile → Look for test/quality/lint targets
   - go.mod → Go project
   - Cargo.toml → Rust project
2. Pre-fill what you can from project files
3. Ask the user to confirm or adjust values
4. Write .devops-ai/project.md using the template structure
```

**Implementation Notes:**
- This guidance goes in the Configuration Loading section of each skill, but only ONE skill needs the full inspection logic — the first skill the user runs will create the config, and subsequent skills will find it
- Add the full inspection logic to ALL skills (since any skill might be the first one used), but keep it concise — refer to the template structure rather than repeating it
- The inspection is not programmatic — it's instructions for the AI agent to read project files and extract values
- Don't try to be exhaustive about project detection — cover the common cases (Python, Node, Go, Rust, Makefile)

**Acceptance Criteria:**
- [ ] All 5 skills can offer to generate config from project inspection
- [ ] Inspection covers Python, Node, Go, Rust, and Makefile-based projects
- [ ] Generated config follows the template structure from `templates/project-config.md`
- [ ] User is asked to confirm/adjust values before writing
- [ ] Config is written to `.devops-ai/project.md`

---

## Task 3.3: Handle Partial Config

**File(s):** All 5 `skills/*/SKILL.md` (modify)
**Type:** CODING
**Estimated time:** 1-2 hours
**Architectural Pattern:** Graceful Degradation

**Description:**
Ensure skills handle partial config gracefully — when `.devops-ai/project.md` exists but is incomplete (missing sections, empty values, "Not configured" markers).

**What to add:**
In the Configuration Loading section, after the "file exists" path, add:

```
If config exists but sections are missing or say "Not configured":
- Use the values that ARE present
- For missing essential values (test commands for ktask/kmilestone):
  Ask the user, just like the no-config path
- For missing optional values (Infrastructure, E2E):
  Skip those sections silently — don't ask, just note what was skipped
- Do NOT offer to update the config file unless the user asks
```

**Implementation Notes:**
- "Essential" vs "optional" differs by skill:
  - kdesign: Paths.design_documents is essential; everything else is optional
  - ktask: Testing.unit_tests and Testing.quality_checks are essential
  - kmilestone: Testing.unit_tests and Testing.quality_checks are essential
  - kdesign-impl-plan: Testing.* is essential; Infrastructure/E2E are optional
  - kdesign-validate: Paths.design_documents is essential
- Don't be noisy about skipped sections — a brief note is enough
- Don't prompt to update config unless asked — the user may have intentionally left sections empty

**Acceptance Criteria:**
- [ ] All 5 skills handle partial config without errors or excessive prompting
- [ ] Essential values are asked for when missing
- [ ] Optional values are skipped silently with brief note
- [ ] Skills don't offer unsolicited config updates
- [ ] "Not configured" in config is treated same as missing section

---

## Task 3.4: Verify Degradation Paths

**File(s):** All 5 `skills/*/SKILL.md` (review)
**Type:** MIXED
**Estimated time:** 1-2 hours

**Description:**
Trace through all degradation scenarios from SCENARIOS.md and verify the skills handle each one correctly.

**Scenarios to verify:**
1. **No config at all** (Scenario 6): Each skill asks for its essentials, offers to create config
2. **Partial config — no infrastructure** (Scenario 7): Skills use what's available, skip infra sections
3. **Partial config — no E2E** (similar): Skills skip E2E sections
4. **Partial config — no testing commands** (new): ktask/kmilestone ask for test commands
5. **Config exists with all "Not configured" markers**: Skills degrade to minimal mode
6. **Malformed config** (Scenario 9): Skills suggest starting from template

**What to verify:**
- Read each skill's Configuration Loading section end-to-end
- Trace each scenario through the loading logic
- Verify no scenario leads to a dead end or confusing behavior
- Fix any gaps found

**Acceptance Criteria:**
- [ ] All 6 degradation scenarios traced through all relevant skills
- [ ] No dead ends or confusing paths
- [ ] Consistent behavior across skills for the same scenario
- [ ] Malformed config handled (suggest template)

---

## Milestone 3 Completion Checklist

- [ ] Task 3.1: No-config behavior added to all skills
- [ ] Task 3.2: Config generation capability added
- [ ] Task 3.3: Partial config handling added
- [ ] Task 3.4: All degradation paths verified
- [ ] E2E test scenario passes (above)
- [ ] M1 E2E test still passes
- [ ] M2 E2E test still passes
- [ ] All files committed
