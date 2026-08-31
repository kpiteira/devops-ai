# devops-ai

Development workflow skills and infrastructure CLI for AI-assisted software engineering.

## What This Is

Two things that work together:

1. **Skills** — Markdown prompts that implement the human–model contract (`docs/designs/v2-contract/CONTRACT.md`): the human owns what and why, a planner model turns intent into signed specs with acceptance tests, an executor model delivers milestones with real autonomy
2. **kinfra** — A Python CLI that manages git worktrees, Docker sandbox slots with port isolation, and a shared observability stack (Jaeger/Grafana/Prometheus)

Skills work with Claude Code, Codex CLI, and GitHub Copilot CLI via the [Agent Skills standard](https://agentskills.io). kinfra is installed globally via `uv` and works from any project.

## How to Use It

The workflow for a new feature — **rigid about outcomes, silent about paths**:

```
1. Plan         /kspec Add wellness reminders — here's what I'm thinking…
                 → Planner session: codebase walkthrough, interview, investigation
                 → Produces a signed intent spec + one work brief per milestone
                 → Authors each milestone's acceptance tests BEFORE implementation

2. Build        /kbuild docs/specs/reminders/briefs/M1-daily-nudge.md
                 → Executor session: the brief + the code is its entire context
                 → Goal loop until the planner's blocking tests pass
                 → Escape valve: contradictions escalate, never get coded around
                 → Delivers the milestone as a PR

3. Close        /kspec close reminders
                 → Fresh-context review: does the whole diff satisfy the INTENT?
                 → Spec archived; acceptance tests optionally promoted to e2e suite
```

There are no task lists — the path from brief to delivered milestone is the executor's
to find. The rigidity lives in contracts, enforced by machines: a CI guard that rejects
brief or acceptance-test edits from any branch but `spec/*`/`replan/*` (the executor can
never grade its own work), structural gates in `make check`, a new-public-symbol signal
on every PR, and amendment flags that keep the human's signature meaningful.

For day-to-day work, a few shortcuts handle the common cases:

```
/kissue 42       → Fetch GitHub issue, branch, test-first implement, PR with "Closes #42"
/kreview         → Assess PR review comments, implement fixes or push back
/kbabysit        → Babysit a PR: request Copilot review, address, loop to merge-ready
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

### Plan and implement a feature

```bash
/kspec Add user authentication — intent dump…    # Planner: spec + briefs + acceptance tests
/kbuild docs/specs/auth/briefs/M1-login.md       # Executor: deliver one milestone
/kspec triage auth                               # Planner: triage a divergence report
/kspec close auth                                # Planner: feature-close review + archive
```

### Work in isolated environments

```bash
kinfra init                          # One-time project setup (or use /kinfra-onboard)
kinfra impl auth/M1                  # Worktree + sandbox for milestone 1
kinfra status                        # Check sandbox health and ports
kinfra done auth-M1                  # Clean up worktree, sandbox, containers
```

## Skills Reference

### Intent-to-delivery pipeline (the v2 contract)

| Command | Purpose |
|---------|---------|
| `/kspec` | Planner sessions: intent → signed spec + work briefs + acceptance tests; also `replan`, `triage`, and `close` modes |
| `/kbuild` | Executor sessions: one work brief in, goal loop against its blocking tests, milestone PR out |

### Issue workflow

| Command | Purpose |
|---------|---------|
| `/kissue <number>` | Implement a GitHub issue: fetch, branch, test, PR with `Closes #N` |
| `/kreview` | Critically assess PR review comments — implement, push back, or discuss (one round) |
| `/kbabysit` | Drive a PR to merge-ready: request Copilot review, wait, address via kreview, re-review, loop until converged, report with TL;DR |

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

`kinfra init` supports `--dry-run` (preview without writing), `--auto` (non-interactive), `--health-endpoint` (custom health check URL), `--no-quality` (skip quality artifacts), and `--check` (report gaps without changes) flags.

### Quality infrastructure

`kinfra init` also generates quality enforcement artifacts alongside sandbox config:

| Artifact | Purpose | Speed |
|----------|---------|-------|
| `Justfile` / `Makefile` | Task runner with `lint`, `quality`, `test-unit`, `check`, `fix`, `setup` targets | — |
| `.githooks/pre-commit` | Runs `make check` before every commit | ~30s |
| `.github/workflows/ci.yml` | Quality + tests on PRs | ~2min |
| `.github/workflows/security.yml` | CodeQL analysis | ~2min |
| `.devops-ai/check_contract_integrity.py` | PR guard: briefs + acceptance tests are planner-owned (`spec/*`, `replan/*` only) | ~1s |
| `.devops-ai/check_public_surface.py` | PR signal: new public symbols annotated for planner review | ~1s |
| `.claude/settings.json` | `TaskCompleted` hook runs `make lint` (~2s) | ~2s |
| `tests/unit/conftest.py` | Blocks `socket.connect` in unit tests (Python only) | — |

Existing files are never overwritten. Use `--no-quality` to skip quality artifact generation.

## Configuration

Skills read `.devops-ai/project.md` from your project root.

| Section | Used By | Required |
|---------|---------|----------|
| **Project** (name, language) | All skills | For context |
| **Testing** (unit tests, quality checks) | kspec, kbuild | Essential |
| **Infrastructure** (start, logs) | kbuild, kworktree | Optional |
| **E2E Testing** (command, catalog) | kspec, kbuild | Optional |
| **Paths** (specs, design docs) | kspec, kbuild | Essential |
| **Project-Specific Patterns** | kbuild | Optional |

Without a config file, skills ask for essential values and skip optional sections.

## How It Works

Skills are markdown prompts that instruct AI coding tools. Each skill reads `.devops-ai/project.md` to adapt to your project. Shared principles (test quality, quality gates, structural gates) live in `rules/` and are auto-loaded into every conversation via `.claude/rules/` symlinks. kinfra is a real Python CLI that manages git and Docker state.

```
devops-ai/                          ~/.claude/skills/ (symlinks)      your-project/
├── skills/                         ├── kspec/ →                      ├── .devops-ai/
│   ├── kspec/SKILL.md ────────────┤── kbuild/ →                     │   ├── project.md
│   ├── kbuild/SKILL.md ──────────┤── kworktree/ →                  │   └── infra.toml
│   ├── kworktree/SKILL.md ────────┤── kinfra-onboard/ →             ├── docs/specs/
│   └── ...                         └── ...                           ├── tests/acceptance/
├── rules/                          ~/.claude/rules/ (symlinks)       └── docker-compose.yml
│   ├── test-quality.md ───────────── test-quality.md →
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
│   ├── kspec/              # Planner: spec + briefs + acceptance tests, triage, close
│   ├── kbuild/             # Executor: one brief → goal loop → milestone PR
│   ├── kissue/             # Bounded issue lane (defects, chores)
│   ├── kreview/            # PR review comment assessment (single round)
│   ├── kbabysit/           # PR review loop orchestration to merge-ready
│   ├── ke2e/               # E2E test catalog knowledge base + agents
│   ├── kworktree/          # Worktree/sandbox management skill
│   └── kinfra-onboard/     # Project onboarding skill
├── rules/                  # Shared principles (auto-loaded via .claude/rules/)
├── templates/              # Project config, structural-gate starter, observability
├── tests/                  # Unit and E2E tests
├── docs/EVOLUTIONS.md      # Framework evolutions backlog
└── docs/designs/           # Design documents, incl. v2-contract/CONTRACT.md
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `kinfra: command not found` | Run `./install.sh` — requires `uv` |
| Skill commands not found | Run `./install.sh` and restart your AI tool |
| Skills not picking up config | Verify `.devops-ai/project.md` exists in your project root |
| Port conflict on `kinfra impl` | Another slot is using that port range — check `kinfra status` |
| Skills not updating after `git pull` | Check symlinks: `ls -la ~/.claude/skills/kspec` should point to devops-ai |
| Observability stack not starting | Ensure Docker is running, then `kinfra observability up` |

## License

TBD
