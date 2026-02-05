# Skill Generalization: Architecture

## Overview

devops-ai is a collection of versioned markdown skill files plus templates. Skills are installed via symlinks to `~/.claude/commands/`. Each project provides a `.claude/config/project.md` prompt that skills load as their first step to adapt to project-specific tooling. No code, no runtime, no framework — just markdown files and a shell script.

## Component Diagram

```
devops-ai repo (versioned, ~/Documents/dev/devops-ai/)
│
├── skills/                        ← Source of truth for all commands
│   ├── kdesign.md
│   ├── kdesign-validate.md
│   ├── kdesign-impl-plan.md
│   ├── kmilestone.md
│   └── ktask.md
│
├── templates/                     ← Bootstrap files for new projects
│   ├── project-config.md          ← Template for .claude/config/project.md
│   └── AGENTS.md.template         ← Template for project AGENTS.md
│
├── install.sh                     ← Creates symlinks
│
└── docs/                          ← Design docs, patterns, genesis
    └── designs/
        └── skill-generalization/
            ├── DESIGN.md
            └── ARCHITECTURE.md

                    │
                    │ install.sh (symlinks)
                    ▼

~/.claude/commands/                ← Where Claude Code discovers commands
├── kdesign.md        → devops-ai/skills/kdesign.md
├── kdesign-validate.md → devops-ai/skills/kdesign-validate.md
├── kdesign-impl-plan.md → devops-ai/skills/kdesign-impl-plan.md
├── kmilestone.md     → devops-ai/skills/kmilestone.md
└── ktask.md          → devops-ai/skills/ktask.md

                    │
                    │ Skills load project config at runtime
                    ▼

<any-project>/
├── AGENTS.md                      ← Project instructions (from template)
└── .claude/
    └── config/
        └── project.md             ← Project-specific configuration prompt
```

### Component Relationships

| Component | Type | Purpose | Used By |
|-----------|------|---------|---------|
| `skills/*.md` | Markdown prompts | Workflow definitions | Claude Code (via symlinks) |
| `templates/project-config.md` | Template | Bootstrap project config | New projects (copy + edit) |
| `templates/AGENTS.md.template` | Template | Bootstrap project instructions | New projects (copy + edit) |
| `install.sh` | Shell script | Create symlinks to ~/.claude/commands/ | User (one-time, re-run on new skills) |
| `.claude/config/project.md` | Per-project prompt | Project-specific commands, paths, capabilities | k* skills (read as first step) |

## Data Flow

### Skill Execution Flow

```
User types: /ktask M1_core.md 1.2
        │
        ▼
Claude Code loads: ~/.claude/commands/ktask.md
        │                (symlink → devops-ai/skills/ktask.md)
        ▼
Skill preamble: "Read .claude/config/project.md"
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
Script creates symlinks:
  ~/.claude/commands/kdesign.md → ~/Documents/dev/devops-ai/skills/kdesign.md
  ~/.claude/commands/ktask.md   → ~/Documents/dev/devops-ai/skills/ktask.md
  ... (all skills)
        │
        ▼
Reports: "Installed 5 skills. Run 'git pull' in devops-ai to update."
```

### New Project Setup Flow

```
User creates new project
        │
        ▼
mkdir -p .claude/config
cp ~/Documents/dev/devops-ai/templates/project-config.md .claude/config/project.md
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

Each generalized skill follows this pattern:

```markdown
# [Command Name]

[Purpose and overview — unchanged from ktrdr originals]

---

## Configuration Loading

**FIRST STEP — Do this before any workflow action.**

1. Read `.claude/config/project.md` from the project root
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
| **kdesign** | Minimal — add config loading preamble, use configured design path |
| **kdesign-validate** | Minimal — add config loading preamble, generalize examples |
| **kdesign-impl-plan** | Moderate — replace make/docker/e2e/psql references with config values, conditional E2E sections |
| **kmilestone** | Moderate — replace make/e2e/quality-checker references, conditional sections |
| **ktask** | Moderate — replace make/docker/e2e references, remove CLI test patterns (move to project config), conditional infrastructure/E2E sections |

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
# install.sh — Symlink devops-ai skills to ~/.claude/commands/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
TARGET_DIR="$HOME/.claude/commands"

mkdir -p "$TARGET_DIR"

for skill in "$SKILLS_DIR"/*.md; do
    name=$(basename "$skill")
    target="$TARGET_DIR/$name"

    if [ -e "$target" ] && [ ! -L "$target" ]; then
        echo "SKIP: $name (non-symlink file exists, use --force to overwrite)"
        continue
    fi

    ln -sf "$skill" "$target"
    echo "OK: $name → $skill"
done

echo ""
echo "Installed. Run 'git pull' in devops-ai to update skills."
```

### AGENTS.md Template

Industry-standard project instructions incorporating the working agreement patterns from our collaboration. Based on the CLAUDE.md.template already in agent-memory, adapted for AGENTS.md naming.

## Graceful Degradation

| Situation | Behavior |
|-----------|----------|
| No `.claude/config/project.md` | Skill asks for essential values (test command, quality command) |
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
| Skills install correctly | install.sh reports all OK, ls -la ~/.claude/commands/ shows symlinks |
| Config loading works | Run /kdesign in a project with config, verify it reads values |
| Graceful degradation | Run /kdesign in a project without config, verify it prompts |
| ktrdr compatibility | Compare generalized skill output with ktrdr original for same task |

## Implementation Planning Summary

### New Components to Create

| Component | Location | Purpose |
|-----------|----------|---------|
| kdesign.md | skills/ | Generalized design command |
| kdesign-validate.md | skills/ | Generalized validation command |
| kdesign-impl-plan.md | skills/ | Generalized implementation planning |
| kmilestone.md | skills/ | Generalized milestone orchestration |
| ktask.md | skills/ | Generalized task execution |
| project-config.md | templates/ | Project config template |
| AGENTS.md.template | templates/ | Project instructions template |
| install.sh | root | Symlink installer |

### Existing Components (ktrdr originals, for reference only)

| Component | Location in ktrdr | Relationship |
|-----------|-------------------|--------------|
| kdesign.md | .claude/commands/ | Source for generalization |
| kdesign-validate.md | .claude/commands/ | Source for generalization |
| kdesign-impl-plan.md | .claude/commands/ | Source for generalization |
| kmilestone.md | .claude/commands/ | Source for generalization |
| ktask.md | .claude/commands/ | Source for generalization |

ktrdr will continue using its own commands until devops-ai is validated and ready for migration.
