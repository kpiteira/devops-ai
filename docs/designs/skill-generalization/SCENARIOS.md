# Skill Generalization: Design Validation

**Date:** 2026-02-05
**Documents Validated:**
- Design: docs/designs/skill-generalization/DESIGN.md
- Architecture: docs/designs/skill-generalization/ARCHITECTURE.md
- Scope: Full design (all 5 skills, templates, install)

## Validation Summary

**Scenarios Validated:** 12 scenarios traced
**Critical Gaps Found:** 11 (all resolved)
**Interface Contracts:** Defined for skill format, project config, install script, cross-skill references

---

## Scenarios

### Happy Paths

1. **New Project Setup (Python/uv)**: User copies config template, fills in Python/uv commands, all k* commands adapt immediately
2. **Complex Project Setup (Docker + E2E)**: User configures infrastructure, E2E agents, custom patterns — skills activate conditional sections
3. **Running /kdesign in configured project**: Skill reads project config, adapts design path, runs standard design workflow
4. **Running /ktask with TDD**: Skill reads config, uses configured test commands (`uv run pytest tests/unit` instead of `make test-unit`), runs RED→GREEN→REFACTOR cycle
5. **Skill Update via Git Pull**: User runs `git pull` in devops-ai, all symlinked skills update globally

### Error Paths

6. **Missing project config**: Skill detects missing `.devops-ai/project.md`, asks for essential values, suggests creating config
7. **Partial config (no infrastructure)**: Skill uses available config, skips infrastructure sections, notes what was skipped
8. **Configured command fails at runtime**: Skill reports failure, asks user to verify configured command
9. **Malformed config file**: Skill detects parse issue, asks user to verify, suggests starting from template

### Edge Cases

10. **Cross-skill references**: kdesign-impl-plan references kdesign-validate — works because both are available via same install
11. **Project-local overrides**: Project has local skill override — local takes priority over global symlink
12. **Multiple projects, different configs**: Each project has its own `.devops-ai/project.md` — skills adapt per-project

### Integration Boundaries (Inform Gap Analysis)

- Skill installed to multiple tools (Claude Code, Codex, Copilot)
- Agent Skills standard compatibility and token budget constraints
- Skill body size vs. recommended limits

---

## Key Decisions Made

These decisions came from conversation and should inform implementation:

1. **Keep the k prefix on all commands**
   - Context: Considered dropping for generalization
   - Choice: `/kdesign`, `/ktask`, `/kmilestone`, `/kdesign-validate`, `/kdesign-impl-plan`
   - Trade-off: Less "generic" but maintains identity

2. **Config as markdown prompt, not YAML**
   - Context: Skills are prompts — config as prompt composes naturally
   - Choice: `.devops-ai/project.md` is a markdown file read by skills
   - Trade-off: No programmatic parsing possible, but none needed

3. **E2E testing deferred to v1**
   - Context: Most projects won't have E2E agent infrastructure initially
   - Choice: Skills include E2E hooks but don't require E2E system
   - Trade-off: Can't validate E2E flows in v0

4. **Extract E2E content to separate prompt file**
   - Context: E2E content in ktask/kmilestone is significant (~150 lines each)
   - Choice: E2E instructions loaded conditionally from a separate .md file
   - Trade-off: One more file to manage, but keeps base skills focused

5. **Accept skill preamble duplication**
   - Context: Config loading section repeated in each skill (~10-15 lines)
   - Choice: Each skill is self-contained with its own config loading
   - Trade-off: Duplication, but each skill works independently

6. **Graceful mini-install when config missing**
   - Context: Better experience than just "config not found"
   - Choice: Skill inspects project (pyproject.toml, package.json, etc.) and offers to create config
   - Trade-off: Mini-install may not get all values right

7. **Portable via Agent Skills standard**
   - Context: Karl wants portability to Codex CLI and GitHub Copilot CLI
   - Choice: Skills use SKILL.md format with YAML frontmatter for cross-tool compatibility
   - Trade-off: Need to research compatibility and token limits

8. **ktrdr migration deferred beyond MVP**
   - Context: Focus on new-project experience first
   - Choice: ktrdr keeps its own commands until devops-ai is proven
   - Trade-off: Can't validate by direct comparison yet

---

## Gap Analysis (Resolved)

All gaps identified during validation have been resolved:

| Gap | Category | Resolution |
|-----|----------|------------|
| GAP-1: Config loading order | Integration | Skills read config as first step, fail gracefully if missing |
| GAP-2: Placeholder substitution | Data Shape | Skills use natural language references, not literal placeholders |
| GAP-3: Skill preamble duplication | Integration | Accept duplication — each skill stands alone |
| GAP-4: E2E content bloat | Integration | Extract E2E content to separate prompt file, load conditionally |
| GAP-5: Cross-skill version mismatch | Integration | Git ensures all skills update together via symlinks |
| GAP-6: First-time install experience | Error Handling | Minimal assumptions in v0; install command in v2 |
| GAP-7: Config generation from project | Error Handling | Offer mini-install: inspect project, offer to create config |
| GAP-8: ktrdr migration path | Integration | Deferred beyond MVP — focus on new projects |
| GAP-9: E2E agent availability | Integration | Defer to v1; skills have hooks but don't require E2E |
| GAP-10: Config prompt vs. structured data | Data Shape | Markdown prompt is correct — skills are prompts reading prompts |
| GAP-11: Skill size and token limits | Integration | M1 research task to verify against Agent Skills spec limits |

---

## Interface Contracts

### Skill File Format

Each skill follows the Agent Skills standard with directory-based structure:

```
skills/
  kdesign/
    SKILL.md
  kdesign-validate/
    SKILL.md
  kdesign-impl-plan/
    SKILL.md
  kmilestone/
    SKILL.md
  ktask/
    SKILL.md
```

**SKILL.md structure:**

```markdown
---
name: kdesign
description: Collaborative design document generation
metadata:
  version: "0.1.0"
---

# Design Generation Command

## Configuration Loading

**FIRST STEP — Do this before any workflow action.**

1. Read `.devops-ai/project.md` from the project root
2. If the file exists, extract configured values
3. If the file does NOT exist, ask for essentials and offer to create one
4. Use configured values throughout this workflow

---

## Workflow

[... skill-specific workflow with [CONFIGURED_VALUE] references ...]
```

### Project Config Format

`.devops-ai/project.md` — markdown prompt loaded by all k* skills:

```markdown
# Project Configuration

This file is read by k* development commands to adapt workflows to this project.

## Project

- **Name:** [project name]
- **Language:** [Python / TypeScript / Go / etc.]
- **Runner:** [uv / npm / go / etc.]

## Testing

- **Unit tests:** [command, e.g., "uv run pytest tests/unit"]
- **Quality checks:** [command, e.g., "uv run ruff check . && uv run mypy ."]
- **Integration tests:** [command, or "Not configured"]

## Infrastructure

[Description, or "This project has no infrastructure."]

- **Start:** [command]
- **Stop:** [command]
- **Logs:** [command]
- **Health check:** [command or URL]

## E2E Testing

[Description, or "E2E testing is not configured for this project."]

## Paths

- **Design documents:** [e.g., "docs/designs/"]
- **Implementation plans:** [e.g., "implementation/" subfolder within design]
- **Handoff files:** [e.g., "Same directory as implementation plans"]

## Project-Specific Patterns

[Conventions that k* commands should follow]
```

### Install Script Interface

```bash
./install.sh [--force] [--target claude|codex|copilot|all]
```

**Default behavior (no flags):**
- Creates directory symlinks to each tool's `skills/` directory (`~/.claude/skills/`, `~/.codex/skills/`, `~/.copilot/skills/`)
- Reports installed skills and skipped conflicts

**--force flag:**
- Overwrites existing non-symlink files

**--target flag:**
- `claude`: Install for Claude Code only
- `codex`: Install for Codex CLI (`~/.codex/skills/`)
- `copilot`: Install for GitHub Copilot CLI (`~/.copilot/skills/`)
- `all`: Install for all detected tools (default)

**Note:** Exact target paths to be confirmed during M1 Agent Skills research.

### Cross-Skill References

| Skill | References | How Handled |
|-------|-----------|-------------|
| kdesign | kdesign-validate (next step) | Text reference: "Run `/kdesign-validate`" |
| kdesign-validate | kdesign-impl-plan (next step) | Text reference: "Run `/kdesign-impl-plan`" |
| kdesign-impl-plan | kdesign, kdesign-validate (inputs), ktask (outputs) | Text references only |
| kmilestone | ktask (invokes per task) | Direct invocation: `/ktask impl: <file> task: <id>` |
| ktask | E2E agents (conditional) | Conditional section, loaded from separate prompt if configured |

### Skill-to-Config Value Mapping

| Skill | Config Values Used |
|-------|-------------------|
| kdesign | Paths.design_documents, Project.name |
| kdesign-validate | Paths.design_documents, Project.name |
| kdesign-impl-plan | Testing.*, Infrastructure.*, E2E.*, Paths.* |
| ktask | Testing.unit_tests, Testing.quality_checks, Infrastructure.*, E2E.* |
| kmilestone | Testing.unit_tests, Testing.quality_checks, E2E.* |

---

## Recommended Milestone Structure

### M1: Foundation + Agent Skills Research (~5 tasks)

**Capability:** Developer can install devops-ai skills and configure a project

**Scope:**
- Research: Agent Skills standard compatibility across Claude Code, Codex CLI, Copilot CLI
- Research: Token limits, SKILL.md format requirements, invocation mechanisms
- Research: Confirm `/kdesign` slash invocation works from `~/.claude/skills/`
- Create: `templates/project-config.md` (project config template)
- Create: `templates/AGENTS.md.template` (project instructions template)
- Create: `install.sh` (multi-tool installer with symlinks)

**E2E Test:**
```
Given: devops-ai cloned, no prior installation
When: User runs ./install.sh
Then: Skills appear in appropriate directories for detected tools
      Symlinks point back to devops-ai/skills/
```

**Depends On:** Nothing

**Key Risk:** Agent Skills standard may have constraints we haven't accounted for. M1 research resolves this before skills are written.

---

### M2: All Five Skills (~8-10 tasks)

**Capability:** All k* commands work in a configured project

**Scope:**
- Generalize: kdesign (SKILL.md format, config loading preamble)
- Generalize: kdesign-validate (SKILL.md format, config loading preamble)
- Generalize: kdesign-impl-plan (SKILL.md format, replace hardcoded commands, conditional sections)
- Generalize: ktask (SKILL.md format, replace hardcoded commands, conditional E2E/infra sections)
- Generalize: kmilestone (SKILL.md format, replace hardcoded commands, conditional sections)

**Task Ordering:**
1. kdesign (smallest changes, validates pattern)
2. kdesign-validate (small changes, validates pattern)
3. kdesign-impl-plan (moderate changes, E2E/infra conditionals)
4. ktask (moderate changes, most ktrdr-specific content)
5. kmilestone (moderate changes, orchestration references)

**E2E Test:**
```
Given: devops-ai installed, project configured with Python/uv
When: User runs /kdesign in Claude Code
Then: Skill loads config, uses configured design path, runs standard workflow
```

**Depends On:** M1 (install + config template + Agent Skills format decision)

---

### M3: Graceful Degradation + Config Generation (~4-5 tasks)

**Capability:** Skills work without config and can help create one

**Scope:**
- No-config behavior: Ask for essential values (test command, quality command)
- Partial-config behavior: Use what's available, ask for missing essentials
- Config generation: Inspect project (pyproject.toml, package.json, Makefile) and offer to create config
- Edge cases: Unknown language, missing sections, empty values

**E2E Test:**
```
Given: devops-ai installed, project WITHOUT .devops-ai/project.md
When: User runs /kdesign
Then: Skill asks for essential values, suggests creating config file
      If user agrees, config is created from project inspection
```

**Depends On:** M2 (skills must exist to add degradation behavior)

---

### M4: Documentation + Polish (~3-4 tasks)

**Capability:** Complete, documented, ready-to-use skill suite

**Scope:**
- README update: Complete quick start, per-skill usage examples, troubleshooting
- Per-skill documentation: Usage patterns, options, what it produces
- Migration notes: How ktrdr would migrate when ready (informational)
- Validation: Run each skill in a test project end-to-end
- Cross-references: Ensure all skills reference each other correctly

**E2E Test:**
```
Given: Fresh clone of devops-ai, following README instructions only
When: New user sets up a project from scratch
Then: All steps work, commands function, documentation is sufficient
```

**Depends On:** M3 (all features complete before final docs)

---

## Appendix: Scenario Traces

### Trace: New Project Setup (Scenario 1)

```
User copies template → .devops-ai/project.md
User edits config → fills in Python/uv values
User runs /ktask → skill loads config
  Step 1: Read .devops-ai/project.md ✓
  Step 2: Extract Testing.unit_tests = "uv run pytest tests/unit" ✓
  Step 3: Extract Testing.quality_checks = "uv run ruff check . && uv run mypy ." ✓
  Step 4: Infrastructure section says "no infrastructure" → skip infra sections ✓
  Step 5: E2E section says "not configured" → skip E2E sections ✓
  Step 6: Execute TDD workflow with configured commands ✓
```

### Trace: Missing Config (Scenario 6)

```
User runs /kdesign → skill tries to read .devops-ai/project.md
  Step 1: File not found
  Step 2: Skill asks: "What command runs your unit tests?"
  Step 3: Skill asks: "What command runs quality/lint checks?"
  Step 4: Skill asks: "Where do you store design documents?"
  Step 5: Skill offers: "Want me to create .devops-ai/project.md with these values?"
  Step 6: If yes → inspects pyproject.toml/package.json for additional context
  Step 7: Creates config file, proceeds with workflow
```

### Trace: Cross-Skill Pipeline (Scenario 10)

```
/kdesign → produces DESIGN.md + ARCHITECTURE.md
  References: "Run /kdesign-validate to validate"
/kdesign-validate → reads DESIGN.md + ARCHITECTURE.md
  Config: Uses Paths.design_documents from project config
  References: "Run /kdesign-impl-plan to plan implementation"
/kdesign-impl-plan → reads DESIGN.md + ARCHITECTURE.md + SCENARIOS.md
  Config: Uses Testing.*, Infrastructure.*, E2E.*, Paths.*
  Produces: Implementation plan with /ktask-compatible task format
  References conditional E2E sections based on E2E.* config
/kmilestone → orchestrates /ktask calls
  Config: Uses Testing.* for verification between tasks
/ktask → executes individual tasks
  Config: Uses Testing.unit_tests, Testing.quality_checks
  Conditional: Infrastructure smoke tests, E2E agent invocations
```

---

*Validated: 2026-02-05*
*Validator: Claude (kdesign-validate process)*
*Reviewer: Karl*
