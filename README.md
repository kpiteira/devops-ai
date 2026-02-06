# devops-ai

Versioned, configuration-driven development workflow skills for AI-assisted software engineering.

## What This Is

A collection of battle-tested development workflow commands that work with Claude Code, Codex CLI, and GitHub Copilot CLI via the [Agent Skills standard](https://agentskills.io):

| Command | Purpose |
|---------|---------|
| `/kdesign` | Collaborative design document generation |
| `/kdesign-validate` | Scenario-based design validation |
| `/kdesign-impl-plan` | Vertical implementation planning |
| `/kmilestone` | Milestone orchestration |
| `/ktask` | TDD task execution with handoffs |

These encode proven patterns: collaborative design, scenario validation, vertical milestones, TDD execution, and handoff continuity.

## Quick Start

### 1. Install skills

```bash
git clone https://github.com/kpiteira/devops-ai.git ~/Documents/dev/devops-ai
cd ~/Documents/dev/devops-ai
./install.sh
```

This symlinks all skills to each tool's `skills/` directory (`~/.claude/skills/`, `~/.codex/skills/`, `~/.copilot/skills/`). Skills follow the [Agent Skills standard](https://agentskills.io) for cross-tool portability.

### 2. Configure a project

```bash
cd /path/to/your/project
mkdir -p .devops-ai
cp ~/Documents/dev/devops-ai/templates/project-config.md .devops-ai/project.md
# Edit .devops-ai/project.md with your project's commands and paths
```

### 3. Use the commands

```bash
# In Claude Code:
/kdesign feature: Add user authentication
/ktask M1_auth.md 1.2
/kmilestone @M1_auth.md
```

## How It Works

Skills are markdown prompts that instruct AI coding tools (Claude Code, Codex, Copilot). Each skill starts by reading your project's `.devops-ai/project.md` to learn project-specific values (test commands, paths, infrastructure). The core workflow patterns are universal; the tooling adapts.

```
devops-ai (versioned)        ~/.claude/skills/ (symlinks)         your-project/
├── skills/                  ├── kdesign/ →                       ├── .devops-ai/
│   ├── kdesign/SKILL.md ───┤── ktask/ →                         │   └── project.md  ← config
│   ├── ktask/SKILL.md ─────┤── kmilestone/ →                    └── AGENTS.md
│   └── ...                  └── ...
```

Same symlinks are created for `~/.codex/skills/` and `~/.copilot/skills/` when those tools are detected.

## Design Principles

1. **Skills are prompts, not code** — No runtime, no framework, just markdown
2. **Config is also a prompt** — `.devops-ai/project.md` is read by skills, not parsed by a program
3. **Symlinks for updates** — `git pull` in devops-ai updates all skills globally
4. **Graceful degradation** — Skills work without config by asking for needed values
5. **Conditional capabilities** — E2E testing, Docker infrastructure are optional
6. **Agent Skills standard** — Cross-tool portable via [agentskills.io](https://agentskills.io) spec

## Relationship to Other Projects

| Project | Purpose | Visibility |
|---------|---------|------------|
| **devops-ai** (this) | Development workflow skills | Public (eventually) |
| **agent-memory** | Memory infrastructure (store, retrieve, consolidate) | Public (eventually) |
| **Lux** | Private memory content | Private |

## Status

Early development. Current focus: generalizing skills from ktrdr-specific to portable.

See: `docs/designs/skill-generalization/` for design and architecture documents.

## License

TBD — considering open source once stable.

---

*Created: 2026-02-04*
