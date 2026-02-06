---
design: docs/designs/skill-generalization/DESIGN.md
architecture: docs/designs/skill-generalization/ARCHITECTURE.md
---

# Milestone 4: Documentation + Polish

**Branch:** `feature/devops-ai-M4-documentation`
**Project Root:** `~/Documents/dev/devops-ai/`
**Goal:** Complete, documented, ready-to-use skill suite that a new user can set up from README alone.

> **All file paths in this plan are relative to the devops-ai repo.**
> This plan is executed from ktrdr (which has the k* commands) but all
> files are created and modified in `~/Documents/dev/devops-ai/`.

**Builds on:** M3 (all features complete)

---

## E2E Validation

### Test Scenario

```bash
# Simulate a new user following README instructions only:

# 1. Verify README has complete quick start
grep -A 20 "Quick Start" README.md | grep -c "install\|configure\|commands"  # should be >= 3

# 2. Verify install works
./install.sh

# 3. Verify template copy works
mkdir -p /tmp/test-project/.devops-ai
cp templates/project-config.md /tmp/test-project/.devops-ai/project.md

# 4. Verify README references all 5 commands
for cmd in kdesign kdesign-validate kdesign-impl-plan kmilestone ktask; do
  grep -q "$cmd" README.md && echo "OK: $cmd" || echo "MISSING: $cmd"
done

# 5. Verify troubleshooting section exists
grep -q "Troubleshooting\|troubleshoot" README.md && echo "OK" || echo "MISSING"

# 6. Cleanup
rm -rf /tmp/test-project
```

**Success Criteria:**
- [ ] README has complete quick start (install → configure → use)
- [ ] All 5 commands documented with usage examples
- [ ] Troubleshooting section covers common issues
- [ ] A new user can set up from README alone

---

## Task 4.1: Update README with Complete Documentation

**File(s):** `README.md` (modify)
**Type:** CODING
**Estimated time:** 2-3 hours

**Description:**
Update the README to be the complete user guide for devops-ai. Currently it has a skeleton quick start. After M1-M3, we have real content to document.

**What to add/update:**
1. **Quick Start** — verify the install → configure → use flow still works with final paths
2. **Per-command documentation** — for each of the 5 commands:
   - What it does (one sentence)
   - When to use it (one sentence)
   - Usage example
   - What it produces
3. **Workflow overview** — how the commands chain together:
   `/kdesign` → `/kdesign-validate` → `/kdesign-impl-plan` → `/kmilestone` → `/ktask`
4. **Configuration guide** — what goes in `.devops-ai/project.md`, section by section
5. **Troubleshooting** — common issues:
   - "Command not found" → run install.sh
   - "Config not found" → create .devops-ai/project.md
   - "Symlink broken" → re-run install.sh
   - Skills not updating → check symlinks, run git pull
6. **Cross-tool usage** — brief note on Codex/Copilot compatibility

**Implementation Notes:**
- Keep it concise — README should be scannable, not a book
- Use the existing structure, don't reorganize unnecessarily
- The per-command docs should be brief — the skills themselves are the detailed docs
- Link to design docs for the curious (`docs/designs/skill-generalization/`)

**Acceptance Criteria:**
- [ ] Quick start is complete and accurate
- [ ] All 5 commands have usage documentation
- [ ] Workflow chain is documented
- [ ] Configuration guide exists
- [ ] Troubleshooting section exists
- [ ] README is < 200 lines (concise)

---

## Task 4.2: Update AGENTS.md

**File(s):** `AGENTS.md` (modify)
**Type:** CODING
**Estimated time:** 1 hour

**Description:**
Update the project's AGENTS.md to reflect the final state of the repository after M1-M3.

**What to update:**
1. **Project Structure** — verify it matches actual file tree (including `skills/shared/`, `implementation/` docs)
2. **Key components** — update descriptions if any changed during implementation
3. Add brief **development workflow** section: how to modify skills, test changes, run install

**Acceptance Criteria:**
- [ ] Project structure matches actual repo
- [ ] All components accurately described
- [ ] Development workflow documented

---

## Task 4.3: End-to-End Validation

**File(s):** None (validation only)
**Type:** VALIDATION
**Estimated time:** 2-3 hours

**Description:**
Run each skill in a test project to verify the complete workflow works end-to-end. This is the final gate before declaring the skill suite ready.

**Validation steps:**
1. **Fresh install test:**
   - Remove existing symlinks
   - Run `./install.sh`
   - Verify all 5 skills appear in `~/.claude/skills/`

2. **New project setup test:**
   - Create a temporary project directory
   - Copy config template, fill in Python/uv values
   - Verify config has all sections

3. **Skill invocation test** (in Claude Code):
   - Run `/kdesign` — verify it reads config, uses configured design path
   - Run `/kdesign-validate` — verify it references the design output
   - Run `/kdesign-impl-plan` — verify it produces milestone files
   - Run `/ktask` — verify it uses configured test commands
   - Run `/kmilestone` — verify it orchestrates ktask calls

4. **No-config test:**
   - Remove config from test project
   - Run `/kdesign` — verify it asks for essentials
   - Verify it offers to create config

5. **Cross-skill reference test:**
   - Verify kdesign references kdesign-validate
   - Verify kdesign-validate references kdesign-impl-plan
   - Verify kdesign-impl-plan produces ktask-compatible output
   - Verify kmilestone invokes ktask with correct syntax

**Acceptance Criteria:**
- [ ] Fresh install works
- [ ] New project setup works following README only
- [ ] All 5 skills invoke successfully with config
- [ ] No-config degradation works
- [ ] Cross-skill references are correct
- [ ] No regressions from M1/M2/M3

---

## Milestone 4 Completion Checklist

- [ ] Task 4.1: README updated
- [ ] Task 4.2: AGENTS.md updated
- [ ] Task 4.3: End-to-end validation passes
- [ ] M1 E2E test still passes
- [ ] M2 E2E test still passes
- [ ] M3 E2E test still passes
- [ ] All files committed
- [ ] Project ready for use
