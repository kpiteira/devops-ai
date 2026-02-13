# devops-ai

Development workflow skills and infrastructure CLI for AI-assisted software engineering.

## What This Is

Two things that work together:

1. **Skills** — Markdown prompts that guide AI coding tools through proven development workflows (design, validate, plan, implement)
2. **kinfra** — A Python CLI that manages git worktrees, Docker sandbox slots with port isolation, and a shared observability stack (Jaeger/Grafana/Prometheus)

Skills work with Claude Code, Codex CLI, and GitHub Copilot CLI via the [Agent Skills standard](https://agentskills.io). kinfra is installed globally via `uv` and works from any project.

## How to Use It

The typical workflow for a new feature:

```
1. Design       /kdesign feature: Add wellness reminders
                 → Collaborative conversation producing DESIGN.md + ARCHITECTURE.md
                 → Validates through scenario tracing, produces milestone structure

2. Plan         /kplan design: DESIGN.md arch: ARCHITECTURE.md
                 → Expands milestones into tasks with files, tests, acceptance criteria

3. Build        /kbuild impl: M1_reminders.md
                 → Executes each task with TDD (red → green → refactor)
                 → Maintains handoff documents between tasks
                 → Produces milestone completion report
```

Each stage produces artifacts consumed by the next. You can enter at any point — `/kbuild` works fine with a hand-written plan, and `/kplan` works with a design you wrote yourself.

For day-to-day work, two shortcuts handle the common cases:

```
/kissue 42       → Fetch GitHub issue, branch, TDD implement, PR with "Closes #42"
/kreview         → Assess PR review comments, implement fixes or push back
```

For projects with Docker infrastructure, kinfra provides isolated environments:

```bash
kinfra impl auth/M1              # Worktree + sandbox with isolated ports
kinfra status                    # Check container health and port mappings
kinfra done auth-M1              # Clean up everything
```

## Contents

- [Install](#install)
- [Getting Started](#getting-started)
- [Skills Reference](#skills-reference)
- [kinfra CLI Reference](#kinfra-cli-reference)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

## Install

**Prerequisites:** [uv](https://docs.astral.sh/uv/), [git](https://git-scm.com/), an AI coding tool ([Claude Code](https://claude.ai/claude-code), [Codex CLI](https://github.com/openai/codex), or [GitHub Copilot CLI](https://docs.github.com/en/copilot)). Docker is only needed for sandbox slots and observability.

```bash
git clone https://github.com/kpiteira/devops-ai.git ~/Documents/dev/devops-ai
cd ~/Documents/dev/devops-ai
./install.sh
```

This does three things:
- **kinfra CLI** — Installed globally via `uv tool install -e .` (editable mode)
- **Skills** — Symlinked to `~/.claude/skills/`, `~/.codex/skills/`, `~/.copilot/skills/`
- **Rules** — Symlinked to `.claude/rules/` in devops-ai itself (shared principles loaded into every conversation)

Use `--target claude` to install for a single tool only. Use `--force` to overwrite non-symlink files. Use `--rules /path/to/project` to install rules into another project.

Verify:

```bash
kinfra --help              # CLI is on PATH
ls ~/.claude/skills/       # Skills are symlinked
```

### Upgrade

Skills are symlinks and kinfra is an editable install, so pulling new code is usually enough:

```bash
cd ~/Documents/dev/devops-ai
git pull
```

If a new skill was added, re-run `./install.sh` to create its symlink. Project-level config (`.devops-ai/project.md`, `infra.toml`) is never touched by upgrades.

## Getting Started

### Set up a new project

For projects with Docker Compose, use the onboarding skill:

```bash
cd /path/to/your/project
/kinfra-onboard                      # Guided 4-phase onboarding
```

This analyzes your project, previews changes, sets up `infra.toml`, parameterizes compose ports, rewires OTEL endpoints, and verifies everything. Use `--check` to just analyze without making changes.

For projects without Docker, create a config manually:

```bash
mkdir -p .devops-ai
cp ~/Documents/dev/devops-ai/templates/project-config.md .devops-ai/project.md
# Edit with your project's test commands and paths
```

Or skip config entirely — skills ask for needed values on first use.

### Design and implement a feature

```bash
/kdesign feature: Add user authentication      # Design + validate
/kplan design: DESIGN.md arch: ARCHITECTURE.md  # Break into tasks
/kbuild impl: M1_auth.md                        # Execute milestone
/kbuild impl: M1_auth.md task: 1.2              # Or a single task
```

### Work in isolated environments

```bash
kinfra init                          # One-time project setup (or use /kinfra-onboard)
kinfra impl auth/M1                  # Worktree + sandbox for milestone 1
kinfra status                        # Check sandbox health and ports
kinfra done auth-M1                  # Clean up worktree, sandbox, containers
```

## Skills Reference

### Design-to-implementation pipeline

| Command | Purpose |
|---------|---------|
| `/kdesign` | Collaborative design and validation — produces DESIGN.md, ARCHITECTURE.md, and a milestone structure |
| `/kplan` | Expand milestones into implementable tasks with architecture alignment and TDD requirements |
| `/kbuild` | Execute tasks (TDD) or orchestrate full milestones from implementation plans |

### Issue workflow

| Command | Purpose |
|---------|---------|
| `/kissue <number>` | Implement a GitHub issue: fetch, branch, TDD, PR with `Closes #N` |
| `/kreview` | Critically assess PR review comments — implement, push back, or discuss |

### Infrastructure

| Command | Purpose |
|---------|---------|
| `/kworktree` | Worktree and sandbox management via kinfra |
| `/kinfra-onboard` | Onboard any project to kinfra's sandbox and observability ecosystem |

## kinfra CLI Reference

A Python CLI for managing isolated development environments across projects.

### Commands

| Command | What it does |
|---------|-------------|
| `kinfra init` | Inspect a project, parameterize compose ports, generate `infra.toml` |
| `kinfra spec <feature>` | Create a spec worktree for design work |
| `kinfra impl <feature/milestone>` | Create an impl worktree with optional Docker sandbox |
| `kinfra done <worktree>` | Clean up worktree, sandbox slot, and Docker containers |
| `kinfra worktrees` | List active worktrees for the project |
| `kinfra status` | Show sandbox slot, ports, and container health |
| `kinfra observability up\|down\|status` | Manage the shared Jaeger/Grafana/Prometheus stack |

### Key capabilities

**Git worktrees** — Isolated branches for spec and implementation work, following `spec/<feature>` and `impl/<feature>-<milestone>` conventions.

**Docker sandbox slots** — Each `kinfra impl` allocates a numbered slot (1-100) with port isolation. Port formula: `base_port + slot_id`. Slots are tracked in a global registry at `~/.devops-ai/registry.json` so multiple projects never collide.

**Shared observability** — A single Jaeger/Grafana/Prometheus stack on dedicated 4xxxx ports (Jaeger UI: 46686, OTLP: 44317, Prometheus: 49090, Grafana: 43000). All sandboxes auto-connect to the `devops-ai-observability` Docker network and export OTEL traces with project-specific namespacing.

**Agent-deck integration** — Optional `--session` flag on `impl`/`done` for agent-deck session management, with graceful degradation when agent-deck isn't installed.

### Onboarding a project

The `/kinfra-onboard` skill provides intelligent, phased onboarding:

1. **Analyze** — Reads compose files, app config, and git state. Reports what it found.
2. **Propose** — Runs `kinfra init --dry-run` to preview changes, plans app-level OTEL rewiring.
3. **Execute** — Runs `kinfra init --auto`, updates OTEL endpoints, modifies project docs.
4. **Verify** — Confirms config validity, compose parsing, and consistency.

`kinfra init` supports `--dry-run` (preview without writing), `--auto` (non-interactive), and `--health-endpoint` (custom health check URL) flags.

## Configuration

Skills read `.devops-ai/project.md` from your project root.

| Section | Used By | Required |
|---------|---------|----------|
| **Project** (name, language) | All skills | For context |
| **Testing** (unit tests, quality checks) | kbuild, kplan | Essential |
| **Infrastructure** (start, logs) | kbuild, kworktree | Optional |
| **E2E Testing** (command, catalog) | kbuild, kplan | Optional |
| **Paths** (design docs) | kdesign, kplan | Essential |
| **Project-Specific Patterns** | kbuild | Optional |

Without a config file, skills ask for essential values and skip optional sections.

## How It Works

Skills are markdown prompts that instruct AI coding tools. Each skill reads `.devops-ai/project.md` to adapt to your project. Shared principles (TDD, quality gates, handoffs) live in `rules/` and are auto-loaded into every conversation via `.claude/rules/` symlinks. kinfra is a real Python CLI that manages git and Docker state.

```
devops-ai/                          ~/.claude/skills/ (symlinks)      your-project/
├── skills/                         ├── kdesign/ →                    ├── .devops-ai/
│   ├── kdesign/SKILL.md ──────────┤── kplan/ →                      │   ├── project.md
│   ├── kplan/SKILL.md ────────────┤── kbuild/ →                     │   └── infra.toml
│   ├── kbuild/SKILL.md ──────────┤── kworktree/ →                  ├── docker-compose.yml
│   ├── kworktree/SKILL.md ────────┤── kinfra-onboard/ →             └── ...
│   └── ...                         └── ...
├── rules/                          ~/.claude/rules/ (symlinks)
│   ├── tdd.md ────────────────────── tdd.md →
│   ├── quality-gates.md ──────────── quality-gates.md →
│   └── ...                           ...
├── src/devops_ai/                  kinfra (global CLI via uv)
│   ├── cli/                        └── manages worktrees, sandboxes,
│   ├── compose.py                     ports, observability
│   └── ...
└── templates/
    ├── project-config.md
    └── observability/docker-compose.yml
```

### Design principles

1. **Skills are prompts, not code** — No runtime, no framework, just markdown
2. **kinfra is deterministic** — The CLI handles mechanical work; skills provide the judgment layer
3. **Config is also a prompt** — `.devops-ai/project.md` is read by skills, not parsed by a program
4. **Symlinks for updates** — `git pull` in devops-ai updates all skills globally
5. **Graceful degradation** — Skills work without config; kinfra features (sandbox, observability) are opt-in
6. **Agent Skills standard** — Cross-tool portable via [agentskills.io](https://agentskills.io) spec

## Project Structure

```
devops-ai/
├── src/devops_ai/          # kinfra CLI source (Python)
│   ├── cli/                # Typer command modules
│   ├── compose.py          # Docker Compose parameterization
│   ├── config.py           # infra.toml loader
│   ├── ports.py            # Port allocation with conflict detection
│   ├── registry.py         # Global slot registry (~/.devops-ai/registry.json)
│   ├── sandbox.py          # Sandbox file generation (.env, overrides)
│   ├── observability.py    # Shared observability stack management
│   ├── worktree.py         # Git worktree lifecycle
│   └── agent_deck.py       # Optional agent-deck integration
├── skills/                 # AI tool skills (symlinked on install)
│   ├── kdesign/            # Design and validation
│   ├── kplan/              # Implementation planning
│   ├── kbuild/             # TDD task execution and milestone orchestration
│   ├── kissue/             # GitHub issue implementation
│   ├── kreview/            # PR review comment assessment
│   ├── kworktree/          # Worktree/sandbox management skill
│   └── kinfra-onboard/     # Project onboarding skill
├── rules/                  # Shared principles (auto-loaded via .claude/rules/)
├── templates/              # Project config and observability templates
├── tests/                  # Unit and E2E tests
└── docs/designs/           # Design documents for devops-ai itself
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `kinfra: command not found` | Run `./install.sh` — requires `uv` |
| Skill commands not found | Run `./install.sh` and restart your AI tool |
| Skills not picking up config | Verify `.devops-ai/project.md` exists in your project root |
| Port conflict on `kinfra impl` | Another slot is using that port range — check `kinfra status` |
| Skills not updating after `git pull` | Check symlinks: `ls -la ~/.claude/skills/kdesign` should point to devops-ai |
| Observability stack not starting | Ensure Docker is running, then `kinfra observability up` |

## License

TBD
