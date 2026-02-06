---
design: docs/designs/skill-generalization/DESIGN.md
architecture: docs/designs/skill-generalization/ARCHITECTURE.md
---

# Milestone 1: Foundation + Agent Skills Research

**Branch:** `feature/devops-ai-M1-foundation`
**Project Root:** `~/Documents/dev/devops-ai/`
**Goal:** Developer can install devops-ai skills and configure a project.

> **All file paths in this plan are relative to the devops-ai repo.**
> This plan is executed from ktrdr (which has the k* commands) but all
> files are created and modified in `~/Documents/dev/devops-ai/`.

**Why this is M1:** Without the install mechanism, templates, and confirmed Agent Skills format, we can't write skills. This proves the distribution architecture.

---

## E2E Validation

### Test Scenario

```bash
# 1. Run installer from a clean state
./install.sh

# 2. Verify symlinks exist and point correctly
ls -la ~/.claude/skills/kdesign/SKILL.md
readlink ~/.claude/skills/kdesign  # should → devops-ai/skills/kdesign/

# 3. Verify all 5 skills installed
ls ~/.claude/skills/ | grep -c "^k"  # should be 5

# 4. Copy template to a test project
mkdir -p /tmp/test-project/.devops-ai
cp templates/project-config.md /tmp/test-project/.devops-ai/project.md

# 5. Verify template has all required sections
grep "## Testing" /tmp/test-project/.devops-ai/project.md
grep "## Infrastructure" /tmp/test-project/.devops-ai/project.md
grep "## Paths" /tmp/test-project/.devops-ai/project.md

# 6. Cleanup
rm -rf /tmp/test-project
```

**Success Criteria:**
- [ ] 5 skill symlinks created in `~/.claude/skills/`
- [ ] All symlinks resolve to `devops-ai/skills/<name>/`
- [ ] Each skill directory contains a valid `SKILL.md`
- [ ] Template copies and contains all documented sections
- [ ] `--force` flag overwrites existing non-symlink files
- [ ] `--target claude` installs only to Claude Code directory

---

## Task 1.1: Research Agent Skills Standard Compatibility

**File(s):** `docs/designs/skill-generalization/research/agent-skills-research.md` (create)
**Type:** RESEARCH
**Estimated time:** 2-3 hours

**Description:**
Investigate the Agent Skills standard (agentskills.io) to resolve the open questions from the design docs. This research gates all subsequent work — if the standard has constraints we haven't accounted for, we need to know before writing skills.

**Research Questions:**
1. **Token limits**: Agent Skills recommends < 5000 tokens. Our skills range 400-900+ lines. Do we need to modularize? What's the actual enforcement?
2. **Claude Code slash invocation**: Does `/kdesign` work from `~/.claude/skills/kdesign/SKILL.md`? Or only from `~/.claude/commands/`?
3. **Codex/Copilot paths**: What are the exact skill discovery paths? Are they `~/.codex/skills/` and `~/.copilot/skills/` as assumed?
4. **Frontmatter fields**: What YAML frontmatter fields does the standard define? Which are required vs optional?
5. **Invocation syntax**: How do different tools invoke skills? Is `/kdesign args` universal?

**Implementation Notes:**
- Check agentskills.io documentation
- Check Claude Code docs for skill discovery
- Check Codex CLI and Copilot CLI docs for skill paths
- If Claude Code doesn't support `/kdesign` from `skills/`, we may need to also symlink to `commands/` as a fallback — document the finding and update ARCHITECTURE.md

**Acceptance Criteria:**
- [ ] All 5 research questions answered with evidence (docs links, tested behavior)
- [ ] Research doc created with findings
- [ ] If any finding contradicts our design, the relevant design doc is updated
- [ ] Install script paths confirmed or corrected

---

## Task 1.2: Create Project Config Template

**File(s):** `templates/project-config.md` (create)
**Type:** CODING
**Estimated time:** 1 hour
**Architectural Pattern:** Config as Prompt

**Description:**
Create the project configuration template that users copy to `.devops-ai/project.md`. This is the config prompt that all k* skills read as their first step.

**What to do:**
Write the template matching the format specified in ARCHITECTURE.md (Project Config Template section). The template should:
- Have clear section headers matching what skills expect
- Include helpful examples in brackets that users replace
- Cover all config values from the Skill-to-Config Value Mapping in SCENARIOS.md
- Include "Not configured" as the default for optional sections (Infrastructure, E2E)

**Content structure** (from ARCHITECTURE.md):
```
# Project Configuration
## Project (name, language, runner)
## Testing (unit, quality, integration)
## Infrastructure (start, stop, logs, health — or "not configured")
## E2E Testing (system, catalog — or "not configured")
## Paths (designs, implementation plans, handoffs)
## Project-Specific Patterns (freeform conventions)
```

**Testing Requirements:**
- Manual: Template is valid markdown
- Manual: All sections from Skill-to-Config Value Mapping are present
- Manual: Default values for optional sections are clear non-values ("Not configured")

**Acceptance Criteria:**
- [ ] `templates/project-config.md` exists
- [ ] Contains all 6 sections (Project, Testing, Infrastructure, E2E, Paths, Patterns)
- [ ] Each section has clear placeholder examples
- [ ] Optional sections default to "not configured" language
- [ ] File is < 60 lines (concise, not bloated)

---

## Task 1.3: Create AGENTS.md Template

**File(s):** `templates/AGENTS.md.template` (create)
**Type:** CODING
**Estimated time:** 1 hour

**Description:**
Create a project instructions template that users copy as their AGENTS.md. This encodes the working agreement patterns from our collaboration into a reusable template.

**What to do:**
Write an AGENTS.md template with:
- Working agreement section (uncertainty, trade-offs, disagreement, context gaps)
- Shared values section (craftsmanship, honesty, decisions together)
- Project-specific placeholder sections (purpose, structure, commands)
- Reference to `.devops-ai/project.md` for project config

**Implementation Notes:**
- Base on the working agreement from `devops-ai/AGENTS.md` but generalized
- Don't include devops-ai-specific content (project structure, skills list)
- Include clear `[REPLACE THIS]` markers for project-specific sections
- Keep the tone collaborative, not corporate

**Acceptance Criteria:**
- [ ] `templates/AGENTS.md.template` exists
- [ ] Contains working agreement and shared values sections
- [ ] Has clear placeholder sections for project-specific content
- [ ] References `.devops-ai/project.md` for config
- [ ] Tone matches our collaborative style

---

## Task 1.4: Create Install Script

**File(s):** `install.sh` (create)
**Type:** CODING
**Estimated time:** 2 hours
**Architectural Pattern:** Symlink Distribution

**Description:**
Create the multi-tool symlink installer. This is the main distribution mechanism — it creates directory symlinks from each tool's skills directory back to the devops-ai repo.

**What to do:**
Write `install.sh` following the spec in ARCHITECTURE.md (Install Script section), with adjustments based on Task 1.1 research findings:
- Parse `--force` and `--target` flags
- For each target tool, create directory symlinks from `~/.<tool>/skills/<name>/` → `devops-ai/skills/<name>/`
- Handle existing files (skip with warning, or overwrite with `--force`)
- Report results clearly

**Implementation Notes:**
- Use `ln -sfn` for directory symlinks (the `-n` flag prevents following existing symlinks)
- Create parent directories with `mkdir -p`
- The script should be idempotent — running it twice produces the same result
- If Task 1.1 reveals Claude Code needs `commands/` too, add that as a target
- Start with Claude Code only confirmed; Codex/Copilot paths from research

**Testing Requirements:**

*Smoke Test:*
```bash
# Run installer
./install.sh --target claude

# Verify symlinks
ls -la ~/.claude/skills/ | grep "^l"  # should show symlinks
readlink ~/.claude/skills/kdesign     # should point to devops-ai/skills/kdesign

# Verify idempotent
./install.sh --target claude          # should succeed without errors

# Verify force flag
mkdir ~/.claude/skills/test-conflict
./install.sh --target claude          # should skip test-conflict
./install.sh --target claude --force  # should overwrite
rm -rf ~/.claude/skills/test-conflict
```

**Acceptance Criteria:**
- [ ] `install.sh` is executable (`chmod +x`)
- [ ] Creates symlinks for all 5 skills to `~/.claude/skills/`
- [ ] `--force` overwrites existing non-symlink files
- [ ] `--target claude` limits to Claude Code only
- [ ] Reports number of skills installed per tool
- [ ] Idempotent — safe to run multiple times
- [ ] Handles missing parent directories (creates them)
- [ ] Does NOT fail if Codex/Copilot are not installed

---

## Task 1.5: Create Stub SKILL.md Files

**File(s):** `skills/kdesign/SKILL.md`, `skills/kdesign-validate/SKILL.md`, `skills/kdesign-impl-plan/SKILL.md`, `skills/ktask/SKILL.md`, `skills/kmilestone/SKILL.md` (create all)
**Type:** CODING
**Estimated time:** 30 min
**Architectural Pattern:** Agent Skills Standard

**Description:**
Create minimal stub SKILL.md files for all 5 skills so the install script has something to symlink. These stubs will be replaced with full content in M2, but they need valid frontmatter now so the install mechanism can be tested end-to-end.

**What to do:**
For each of the 5 skills, create a minimal SKILL.md with:
- Valid YAML frontmatter (name, description, version: 0.1.0)
- A one-line body noting this is a stub pending M2 implementation

**Content per stub:**
```markdown
---
name: kdesign
description: Collaborative design document generation
version: 0.1.0
---

# Design Generation Command

Stub — full implementation in M2.
```

Repeat for all 5 skills with appropriate name/description.

**Acceptance Criteria:**
- [ ] All 5 skill directories exist: `skills/kdesign/`, `skills/kdesign-validate/`, `skills/kdesign-impl-plan/`, `skills/ktask/`, `skills/kmilestone/`
- [ ] Each contains a `SKILL.md` with valid YAML frontmatter
- [ ] Frontmatter has `name`, `description`, and `version` fields
- [ ] Install script successfully symlinks all 5

---

## Milestone 1 Completion Checklist

- [ ] Task 1.1: Agent Skills research complete, findings documented
- [ ] Task 1.2: `templates/project-config.md` created
- [ ] Task 1.3: `templates/AGENTS.md.template` created
- [ ] Task 1.4: `install.sh` created and working
- [ ] Task 1.5: All 5 stub SKILL.md files created
- [ ] E2E test scenario passes (above)
- [ ] Design docs updated if research reveals discrepancies
- [ ] All files committed
