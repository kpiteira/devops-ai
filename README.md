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

This symlinks all skills to each tool's `skills/` directory (`~/.claude/skills/`, `~/.codex/skills/`, `~/.copilot/skills/`). Use `--target claude` to install for a single tool only.

### 2. Configure a project

```bash
cd /path/to/your/project
mkdir -p .devops-ai
cp ~/Documents/dev/devops-ai/templates/project-config.md .devops-ai/project.md
# Edit .devops-ai/project.md with your project's commands and paths
```

Or skip this step — skills will ask for needed values and offer to create the config.

### 3. Use the commands

```bash
# In Claude Code (or Codex, Copilot):
/kdesign feature: Add user authentication
/kdesign-validate design: DESIGN.md arch: ARCHITECTURE.md
/kdesign-impl-plan design: DESIGN.md arch: ARCHITECTURE.md
/kmilestone @M1_auth.md
/ktask M1_auth.md 1.2
```

## Workflow

The commands chain together in a design-to-implementation pipeline:

```
/kdesign          → DESIGN.md + ARCHITECTURE.md    (what + how)
/kdesign-validate → SCENARIOS.md                    (does it hold up?)
/kdesign-impl-plan → M1_*.md, M2_*.md, ...         (vertical milestones)
/kmilestone        → orchestrates /ktask per task    (execute milestone)
/ktask             → TDD implementation + handoffs   (execute task)
```

Each stage produces artifacts consumed by the next. You can enter at any point — `/ktask` works fine standalone with a hand-written task list.

## Commands

### `/kdesign`

Generates DESIGN.md and ARCHITECTURE.md through collaborative exploration. Asks clarifying questions, proposes options with trade-offs, pauses for alignment at each stage.

**Produces:** `DESIGN.md`, `ARCHITECTURE.md` in configured design path.

### `/kdesign-validate`

Walks through concrete scenarios against the design, catching gaps before implementation. Traces execution paths, identifies missing state transitions, and produces interface contracts.

**Produces:** `SCENARIOS.md` with validated scenarios and milestone structure.

### `/kdesign-impl-plan`

Generates vertical implementation plans where each milestone delivers an E2E-testable capability. Includes detailed tasks with files, acceptance criteria, and test requirements.

**Produces:** One file per milestone (`M1_*.md`, `M2_*.md`, ...) plus `OVERVIEW.md`.

### `/kmilestone`

Orchestrates execution of an entire milestone by invoking `/ktask` for each task. Tracks progress via handoff files, verifies quality gates between tasks, and produces a completion summary.

**Usage:** `/kmilestone @M1_foundation.md`

### `/ktask`

Implements individual tasks using TDD methodology: RED (write failing tests) → GREEN (minimal implementation) → REFACTOR (clean up). Updates handoff documents for context continuity.

**Usage:** `/ktask M1_foundation.md 1.2`

## Configuration

Skills read `.devops-ai/project.md` from your project root. Copy the template from `templates/project-config.md` and fill in your values.

**Sections:**

| Section | Used By | Required |
|---------|---------|----------|
| **Project** (name, language) | All skills | For context |
| **Testing** (unit tests, quality checks) | ktask, kmilestone, kdesign-impl-plan | Essential |
| **Infrastructure** (start, logs) | ktask | Optional |
| **E2E Testing** (system, catalog) | ktask, kmilestone, kdesign-impl-plan | Optional |
| **Paths** (design docs) | kdesign, kdesign-validate, kdesign-impl-plan | Essential |
| **Project-Specific Patterns** | ktask | Optional |

Without a config file, skills ask for essential values and skip optional sections.

## How It Works

Skills are markdown prompts that instruct AI coding tools. Each skill starts by reading your project's `.devops-ai/project.md` to learn project-specific values. The core workflow patterns are universal; the tooling adapts.

```
devops-ai (versioned)        ~/.claude/skills/ (symlinks)         your-project/
├── skills/                  ├── kdesign/ →                       ├── .devops-ai/
│   ├── kdesign/SKILL.md ───┤── ktask/ →                         │   └── project.md  ← config
│   ├── ktask/SKILL.md ─────┤── kmilestone/ →                    └── ...
│   └── ...                  └── ...
```

Same symlinks are created for `~/.codex/skills/` and `~/.copilot/skills/`.

## Design Principles

1. **Skills are prompts, not code** — No runtime, no framework, just markdown
2. **Config is also a prompt** — `.devops-ai/project.md` is read by skills, not parsed by a program
3. **Symlinks for updates** — `git pull` in devops-ai updates all skills globally
4. **Graceful degradation** — Skills work without config by asking for needed values
5. **Conditional capabilities** — E2E testing, Docker infrastructure are optional
6. **Agent Skills standard** — Cross-tool portable via [agentskills.io](https://agentskills.io) spec

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Command not found" when using `/kdesign` etc. | Run `./install.sh` from the devops-ai directory |
| Skills not picking up config | Verify `.devops-ai/project.md` exists in your project root |
| Skills not updating after `git pull` | Check symlinks: `ls -la ~/.claude/skills/kdesign` should point to devops-ai |
| Broken symlinks after moving devops-ai | Re-run `./install.sh` |
| Skills ask for values that are in config | Check for "Not configured" placeholders — replace them with actual values |

## Relationship to Other Projects

| Project | Purpose | Visibility |
|---------|---------|------------|
| **devops-ai** (this) | Development workflow skills | Public (eventually) |
| **agent-memory** | Memory infrastructure (store, retrieve, consolidate) | Public (eventually) |

## Status

Early development. Current focus: generalizing skills from project-specific to portable.

See `docs/designs/skill-generalization/` for design and architecture documents.

## License

TBD — considering open source once stable.
