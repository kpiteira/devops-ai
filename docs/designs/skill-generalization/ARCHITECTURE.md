# Skill Generalization: Architecture

## Overview

devops-ai is a collection of versioned markdown skill files plus templates, following the open [Agent Skills standard](https://agentskills.io) for cross-tool portability. Skills are installed via symlinks to each tool's skills directory (`~/.claude/skills/`, `~/.codex/skills/`, `~/.copilot/skills/`). Each project provides a `.devops-ai/project.md` prompt that skills load as their first step to adapt to project-specific tooling. No code, no runtime, no framework — just markdown files and a shell script.

## Component Diagram

```
devops-ai repo (versioned, ~/Documents/dev/devops-ai/)
│
├── skills/                        ← Source of truth for all commands
│   ├── kdesign/
│   │   └── SKILL.md              ← Agent Skills standard format
│   ├── kdesign-validate/
│   │   └── SKILL.md
│   ├── kdesign-impl-plan/
│   │   └── SKILL.md
│   ├── kmilestone/
│   │   └── SKILL.md
│   └── ktask/
│       └── SKILL.md
│
├── templates/                     ← Bootstrap files for new projects
│   ├── project-config.md          ← Template for .devops-ai/project.md
│   └── AGENTS.md.template         ← Template for project AGENTS.md
│
├── install.sh                     ← Creates symlinks (multi-tool)
│
└── docs/                          ← Design docs, patterns, genesis
    └── designs/
        └── skill-generalization/
            ├── DESIGN.md
            ├── ARCHITECTURE.md
            └── SCENARIOS.md

                    │
                    │ install.sh (symlinks to each tool's skills/ dir)
                    ▼

~/.claude/skills/                  ← Claude Code (Agent Skills standard)
├── kdesign/          → devops-ai/skills/kdesign/
├── kdesign-validate/ → devops-ai/skills/kdesign-validate/
├── kdesign-impl-plan/→ devops-ai/skills/kdesign-impl-plan/
├── kmilestone/       → devops-ai/skills/kmilestone/
└── ktask/            → devops-ai/skills/ktask/

~/.codex/skills/                   ← Codex CLI (if installed)
├── kdesign/          → devops-ai/skills/kdesign/
├── ...

~/.copilot/skills/                 ← GitHub Copilot CLI (if installed)
├── kdesign/          → devops-ai/skills/kdesign/
├── ...

                    │
                    │ Skills load project config at runtime
                    ▼

<any-project>/
├── AGENTS.md                      ← Project instructions (from template)
└── .devops-ai/
    └── project.md                 ← Project-specific configuration prompt
```

**Note:** Exact paths for Codex and Copilot to be confirmed during M1 Agent Skills research. The diagram shows the intended multi-tool architecture.

### Component Relationships

| Component | Type | Purpose | Used By |
|-----------|------|---------|---------|
| `skills/*/SKILL.md` | Markdown prompts (Agent Skills format) | Workflow definitions | Claude Code, Codex, Copilot (via symlinks) |
| `templates/project-config.md` | Template | Bootstrap project config | New projects (copy + edit) |
| `templates/AGENTS.md.template` | Template | Bootstrap project instructions | New projects (copy + edit) |
| `install.sh` | Shell script | Create symlinks to all detected tool directories | User (one-time, re-run on updates) |
| `.devops-ai/project.md` | Per-project prompt | Project-specific commands, paths, capabilities | k* skills (read as first step) |

## Agent Skills Standard

### Why Agent Skills

The [Agent Skills specification](https://agentskills.io) is an open standard adopted by Claude Code, Codex CLI, GitHub Copilot CLI, Cursor, and others. By following this standard:

- Skills work across multiple AI coding tools
- Users familiar with one tool can use skills in another
- Installation targets multiple tools from a single source

### SKILL.md Format

Each skill uses the directory-based format with YAML frontmatter:

```markdown
---
name: kdesign
description: Collaborative design document generation
version: 0.1.0
---

# Design Generation Command

[skill content...]
```

### Open Questions (M1 Research)

These questions will be resolved by M1 research tasks before skills are written:

1. **Token limits**: Agent Skills recommends < 5000 tokens for body. Our skills range from 400-900+ lines. Do we need to modularize?
2. **Claude Code slash invocation from skills/**: Does `/kdesign` invocation work from `~/.claude/skills/kdesign/SKILL.md`? This is our primary install target.
3. **Codex/Copilot paths**: What are the exact skill discovery paths for Codex CLI and Copilot CLI?
4. **Frontmatter fields**: What additional YAML frontmatter fields are useful (tags, author, etc.)?

## Data Flow

### Skill Execution Flow

```
User types: /ktask M1_core.md 1.2
        │
        ▼
Tool loads: ~/.claude/skills/ktask/SKILL.md
        │           (symlink → devops-ai/skills/ktask/SKILL.md)
        ▼
Skill preamble: "Read .devops-ai/project.md"
        │
        ▼
Claude reads project config, learns:
  - Unit tests: uv run pytest tests/unit
  - Quality: uv run ruff check . && uv run mypy .
  - No Docker infrastructure
  - No E2E agents
        │
        ▼
Skill executes TDD workflow with adapted commands
  (uses "uv run pytest tests/unit" not "make test-unit")
  (skips infrastructure sections)
  (skips E2E sections)
```

### Installation Flow

```
User clones devops-ai to ~/Documents/dev/devops-ai/
        │
        ▼
Runs: ./install.sh
        │
        ▼
Script detects installed tools:
  - Claude Code? → target ~/.claude/skills/
  - Codex CLI?   → target ~/.codex/skills/
  - Copilot CLI? → target ~/.copilot/skills/
        │
        ▼
Creates directory symlinks for each target:
  ~/.claude/skills/kdesign/ → devops-ai/skills/kdesign/
  ~/.codex/skills/kdesign/  → devops-ai/skills/kdesign/
  ... (all skills, all detected tools)
        │
        ▼
Reports: "Installed 5 skills for: Claude Code, Codex. Run 'git pull' to update."
```

### New Project Setup Flow

```
User creates new project
        │
        ▼
mkdir -p .devops-ai
cp ~/Documents/dev/devops-ai/templates/project-config.md .devops-ai/project.md
        │
        ▼
Edits project.md with project-specific values
        │
        ▼
Optionally: cp ~/Documents/dev/devops-ai/templates/AGENTS.md.template ./AGENTS.md
        │
        ▼
k* commands now adapt to this project
```

## Components

### Skill File Structure

Each generalized skill follows the Agent Skills standard with a configuration loading preamble:

```markdown
---
name: [skill-name]
description: [one-line description]
version: 0.1.0
---

# [Command Name]

[Purpose and overview — preserved from ktrdr originals]

---

## Configuration Loading

**FIRST STEP — Do this before any workflow action.**

1. Read `.devops-ai/project.md` from the project root
2. If the file exists, extract:
   - Testing commands (unit, quality, integration)
   - Infrastructure details (if any)
   - E2E testing capability (if any)
   - Path conventions
   - Project-specific patterns
3. If the file does NOT exist:
   - Ask the user: "What command runs your unit tests?"
   - Ask the user: "What command runs quality/lint checks?"
   - Suggest creating a config file for future sessions
4. Use the configured values throughout this workflow

**References in the workflow below use placeholders like [UNIT_TEST_COMMAND]
which are replaced by values from the project config.**

---

## Workflow

[Same proven workflow from ktrdr, with hardcoded commands replaced:]

- "make test-unit" → [UNIT_TEST_COMMAND]
- "make quality" → [QUALITY_COMMAND]
- "docker compose up -d" → [INFRA_START_COMMAND] (if infrastructure configured)
- "docker compose logs..." → [INFRA_LOGS_COMMAND] (if infrastructure configured)

[Conditional sections clearly marked:]

### Integration Smoke Test (if infrastructure configured)

[Only applies when project config declares infrastructure]

### E2E Test Execution (if e2e configured)

[Only applies when project config declares e2e capability]
```

### What Changes Per Skill

| Skill | Changes from ktrdr Original |
|-------|----------------------------|
| **kdesign** | Minimal — add frontmatter + config loading preamble, use configured design path |
| **kdesign-validate** | Minimal — add frontmatter + config loading preamble, generalize examples |
| **kdesign-impl-plan** | Moderate — add frontmatter, replace make/docker/e2e/psql references with config values, conditional E2E sections |
| **kmilestone** | Moderate — add frontmatter, replace make/e2e/quality-checker references, conditional sections |
| **ktask** | Moderate — add frontmatter, replace make/docker/e2e references, move CLI test patterns to project config, conditional infrastructure/E2E sections |

### Project Config Template

The template provides a complete, documented config prompt:

```markdown
# Project Configuration

This file is read by k* development commands (kdesign, ktask, kmilestone, etc.)
to adapt workflows to this project's specific tooling and conventions.

## Project

- **Name:** [project name]
- **Language:** [Python / TypeScript / Go / etc.]
- **Runner:** [uv / npm / go / etc.] — prefix for running commands

## Testing

- **Unit tests:** [command, e.g., "uv run pytest tests/unit"]
- **Quality checks:** [command, e.g., "uv run ruff check . && uv run mypy ."]
- **Integration tests:** [command, or "Not configured"]

## Infrastructure

[Describe infrastructure, or state "This project has no infrastructure."]

- **Start:** [command to start services]
- **Stop:** [command to stop services]
- **Logs:** [command to view recent logs]
- **Health check:** [command or URL to verify services are running]

## E2E Testing

[Describe E2E capability, or state "E2E testing is not configured for this project."]

When configured:
- **System:** [agent / manual / framework-name]
- **Test catalog:** [path to test catalog]

## Paths

- **Design documents:** [e.g., "docs/designs/"]
- **Implementation plans:** [e.g., "implementation/" subfolder within design]
- **Handoff files:** [e.g., "Same directory as implementation plans"]

## Project-Specific Patterns

[Add any project-specific conventions that k* commands should follow.
These are loaded as additional context for all commands.]

Examples:
- "Always use the runner fixture for CLI tests (strips ANSI codes)"
- "Never kill processes on port 8000 (Docker container)"
- "Use uv run for all Python commands"
```

### Install Script

```bash
#!/bin/bash
# install.sh — Symlink devops-ai skills to AI tool directories
#
# Usage: ./install.sh [--force] [--target claude|codex|copilot|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
FORCE=false
TARGET="all"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force) FORCE=true; shift ;;
        --target) TARGET="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

install_skills() {
    local target_dir="$1"
    local tool_name="$2"
    local count=0

    mkdir -p "$target_dir"

    for skill_dir in "$SKILLS_DIR"/*/; do
        [ -d "$skill_dir" ] || continue
        name=$(basename "$skill_dir")
        target="$target_dir/$name"

        if [ -e "$target" ] && [ ! -L "$target" ]; then
            if [ "$FORCE" = true ]; then
                rm -rf "$target"
            else
                echo "  SKIP: $name (non-symlink exists, use --force to overwrite)"
                continue
            fi
        fi

        ln -sfn "$skill_dir" "$target"
        echo "  OK: $name"
        count=$((count + 1))
    done

    echo "  → $count skills installed for $tool_name"
}

echo "devops-ai skill installer"
echo ""

# Claude Code
if [ "$TARGET" = "all" ] || [ "$TARGET" = "claude" ]; then
    echo "Claude Code:"
    install_skills "$HOME/.claude/skills" "Claude Code"
    echo ""
fi

# Codex CLI
if [ "$TARGET" = "all" ] || [ "$TARGET" = "codex" ]; then
    echo "Codex CLI:"
    install_skills "$HOME/.codex/skills" "Codex CLI"
    echo ""
fi

# Copilot CLI
if [ "$TARGET" = "all" ] || [ "$TARGET" = "copilot" ]; then
    echo "GitHub Copilot CLI:"
    install_skills "$HOME/.copilot/skills" "Copilot CLI"
    echo ""
fi

echo "Done. Run 'git pull' in devops-ai to update all skills."
```

**Note:** Exact Codex/Copilot paths to be confirmed during M1 research. The script structure supports easy path updates.

### AGENTS.md Template

Industry-standard project instructions incorporating the working agreement patterns from our collaboration. Based on the CLAUDE.md.template in agent-memory, adapted for AGENTS.md naming.

## Graceful Degradation

| Situation | Behavior |
|-----------|----------|
| No `.devops-ai/project.md` | Skill asks for essential values (test command, quality command) |
| Config exists but incomplete | Skill uses what's there, asks for missing essentials |
| E2E not configured | Skill skips E2E sections, notes "E2E not configured" |
| Infrastructure not configured | Skill skips infrastructure sections |
| Unknown language/runner | Skill asks how to run commands |

## Error Handling

| Situation | Error Type | Behavior |
|-----------|------------|----------|
| Config file malformed | Parse issue | Ask user to verify config, suggest template |
| Symlink broken | Installation issue | Inform user, suggest re-running install.sh |
| Configured command fails | Runtime issue | Report failure, ask user to verify command |
| Skill references unavailable capability | Config mismatch | Skip section, note what was skipped |

## Verification Approach

| Component | How to Verify |
|-----------|---------------|
| Skills install correctly | install.sh reports all OK, ls -la shows symlinks |
| Config loading works | Run /kdesign in a project with config, verify it reads values |
| Graceful degradation | Run /kdesign in a project without config, verify it prompts |
| Multi-tool install | Check skill symlinks exist in claude/codex/copilot directories |
| ktrdr compatibility | Compare generalized skill output with ktrdr original for same task |

## Implementation Planning Summary

### Milestones

| # | Name | Scope | Depends On |
|---|------|-------|------------|
| M1 | Foundation + Agent Skills Research | Templates, install script, Agent Skills compatibility research | Nothing |
| M2 | All Five Skills | kdesign, kdesign-validate, kdesign-impl-plan, ktask, kmilestone | M1 |
| M3 | Graceful Degradation + Config Generation | No-config behavior, partial config, config auto-generation | M2 |
| M4 | Documentation + Polish | README, per-skill docs, migration notes, validation | M3 |

### New Components to Create

| Component | Location | Purpose |
|-----------|----------|---------|
| kdesign/SKILL.md | skills/kdesign/ | Generalized design command |
| kdesign-validate/SKILL.md | skills/kdesign-validate/ | Generalized validation command |
| kdesign-impl-plan/SKILL.md | skills/kdesign-impl-plan/ | Generalized implementation planning |
| kmilestone/SKILL.md | skills/kmilestone/ | Generalized milestone orchestration |
| ktask/SKILL.md | skills/ktask/ | Generalized task execution |
| e2e-prompt.md | skills/shared/ | E2E testing instructions, loaded conditionally by ktask/kmilestone |
| project-config.md | templates/ | Project config template |
| AGENTS.md.template | templates/ | Project instructions template |
| install.sh | root | Multi-tool symlink installer |

### Existing Components (ktrdr originals, for reference only)

| Component | Location in ktrdr | Relationship |
|-----------|-------------------|--------------|
| kdesign.md | .claude/commands/ | Source for generalization |
| kdesign-validate.md | .claude/commands/ | Source for generalization |
| kdesign-impl-plan.md | .claude/commands/ | Source for generalization |
| kmilestone.md | .claude/commands/ | Source for generalization |
| ktask.md | .claude/commands/ | Source for generalization |

ktrdr will continue using its own commands until devops-ai is validated and ready for migration.
