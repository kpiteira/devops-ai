# kinfra-onboard: Architecture

## Overview

kinfra-onboard is a Claude Code skill (SKILL.md) that orchestrates project onboarding to the kinfra ecosystem. It has two deliverables: (1) the skill itself, and (2) `--dry-run` and `--auto` flags added to `kinfra init` so the skill can drive it programmatically.

The skill is the intelligence layer — it reads the project, assesses safety, decides what to do, presents a plan, and handles adaptive changes. `kinfra init` remains the deterministic tool that owns compose rewriting and `infra.toml` generation.

## Component Diagram

```
┌─────────────────────────────────────────────────────┐
│  Claude Code session                                │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  /kinfra-onboard skill (SKILL.md)             │  │
│  │                                               │  │
│  │  Phase 1: Analyze                             │  │
│  │    ├─ read compose, project.md, app config    │  │
│  │    ├─ check git state                         │  │
│  │    ├─ detect existing kinfra config           │  │
│  │    └─ report findings                         │  │
│  │                                               │  │
│  │  Phase 2: Propose                             │  │
│  │    ├─ run: kinfra init --dry-run --auto       │  │
│  │    ├─ identify app-level OTEL changes         │  │
│  │    └─ present full plan to user               │  │
│  │                                               │  │
│  │  Phase 3: Execute                             │  │
│  │    ├─ run: kinfra init --auto                 │  │
│  │    ├─ adapt app OTEL config                   │  │
│  │    ├─ update project.md                       │  │
│  │    └─ update relevant docs/skills             │  │
│  │                                               │  │
│  │  Phase 4: Verify & Commit                     │  │
│  │    ├─ validate infra.toml                     │  │
│  │    ├─ validate compose parses                 │  │
│  │    ├─ check config consistency                │  │
│  │    └─ git commit                              │  │
│  └───────────────────────────────────────────────┘  │
│           │                                         │
│           │ shell: kinfra init --dry-run --auto     │
│           │ shell: kinfra init --auto               │
│           ▼                                         │
│  ┌───────────────────────────────────────────────┐  │
│  │  kinfra CLI (existing + new flags)            │  │
│  │                                               │  │
│  │  init_cmd.py                                  │  │
│  │    ├─ --dry-run: preview changes to stdout    │  │
│  │    ├─ --auto: accept defaults, no prompts     │  │
│  │    ├─ detect project name                     │  │
│  │    ├─ find/parse compose                      │  │
│  │    ├─ identify obs services                   │  │
│  │    ├─ generate infra.toml                     │  │
│  │    └─ rewrite compose (parameterize + comment)│  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Component Relationships (Structured Summary)

| Component | Type | Depends On | Used By |
|-----------|------|------------|---------|
| SKILL.md (kinfra-onboard) | Skill file | kinfra CLI, project files | Claude Code user |
| kinfra init --dry-run | CLI flag | init_cmd.py internals | Skill Phase 2 |
| kinfra init --auto | CLI flag | init_cmd.py internals | Skill Phase 3 |
| init_cmd.py | Python module | compose.py, config.py | CLI entry point, skill |

## Components

### SKILL.md (kinfra-onboard skill)

**Location:** `skills/kinfra-onboard/SKILL.md`
**Purpose:** Instructs Claude Code how to run the phased onboarding workflow.
**Key behaviors:**
- Phase 1 (Analyze): Read project files, check safety, report findings
- Phase 2 (Propose): Run `kinfra init --dry-run --auto`, identify OTEL changes, present plan
- Phase 3 (Execute): Run `kinfra init --auto`, make app-level changes, update project.md
- Phase 4 (Verify & Commit): Validate results, create git commit
- --check mode: Run Phase 1 only, skip the rest

**Interface:** Invoked as `/kinfra-onboard [--check]`

### kinfra init --dry-run flag

**Location:** `src/devops_ai/cli/init_cmd.py`
**Purpose:** Preview all changes kinfra init would make without writing any files.
**Key behaviors:**
- Runs the full detection pipeline (project name, compose, services, ports, obs services)
- Prints what infra.toml would contain
- Prints what compose changes would be made (port parameterization, commented services)
- Exits without writing anything

### kinfra init --auto flag

**Location:** `src/devops_ai/cli/init_cmd.py`
**Purpose:** Accept all defaults and skip interactive prompts.
**Key behaviors:**
- Uses detected project name without prompting
- Uses first compose file found without prompting
- Uses default health endpoint `/api/v1/health` without prompting
- Uses project name as worktree prefix without prompting
- Auto-confirms config update if existing config found
- All other logic identical to interactive mode

## Data Flow

```
User: /kinfra-onboard
        │
        ▼
Phase 1: ANALYZE
        │
        ├─ read .devops-ai/project.md
        ├─ read .devops-ai/infra.toml (if exists → already onboarded?)
        ├─ read docker-compose*.yml
        ├─ read app config files (config.yaml, .env, etc.)
        ├─ run: git status --porcelain
        ├─ run: docker compose config (validate compose)
        │
        ▼
   Report findings to user
        │
        ▼
Phase 2: PROPOSE
        │
        ├─ run: kinfra init --dry-run --auto
        │       └─ captures stdout: planned infra.toml + compose changes
        ├─ identify OTEL endpoint in app config
        ├─ identify docs/skills referencing local obs
        │
        ▼
   Present full change plan to user
        │
   ── user approves? ──
        │ yes              │ no
        ▼                  ▼
Phase 3: EXECUTE        (abort)
        │
        ├─ run: kinfra init --auto
        │       └─ writes infra.toml, rewrites compose
        ├─ edit app OTEL config (endpoint → shared stack)
        ├─ edit project.md (add Infrastructure section)
        ├─ edit docs/skills referencing local obs endpoints
        │
        ▼
Phase 4: VERIFY & COMMIT
        │
        ├─ validate: infra.toml exists and parses
        ├─ validate: docker compose config (compose still valid)
        ├─ validate: OTEL endpoint references consistent
        ├─ run: git add <changed files>
        ├─ run: git commit -m "chore: onboard to kinfra sandbox and shared observability"
        │
        ▼
   Report summary to user
```

**Flow Steps (Structured Summary):**

1. Skill reads project files (compose, project.md, app config, git status)
2. Skill reports findings and checks for blockers (dirty git, no compose, already onboarded)
3. Skill runs `kinfra init --dry-run --auto` to preview deterministic changes
4. Skill identifies additional adaptive changes needed (OTEL endpoints, docs)
5. Skill presents combined plan to user for approval
6. On approval: skill runs `kinfra init --auto` for deterministic changes
7. Skill makes adaptive changes (edit app config, project.md, docs)
8. Skill validates all changes (config parses, compose valid, references consistent)
9. Skill creates git commit with all changes

## State Management

| State | Where | Lifecycle |
|-------|-------|-----------|
| Project analysis results | Skill conversation context | Created in Phase 1, used through Phase 4 |
| kinfra init dry-run output | Captured stdout | Created in Phase 2, presented to user |
| Changed file list | Skill conversation context | Accumulated in Phase 3, used for git commit in Phase 4 |
| .devops-ai/infra.toml | Project filesystem | Created by kinfra init in Phase 3 |
| docker-compose.yml.bak | Project filesystem | Created by kinfra init in Phase 3 (backup) |

## Error Handling

| Situation | Phase | Behavior |
|-----------|-------|----------|
| No compose file found | 1 (Analyze) | Report, offer worktree-only setup (infra.toml with has_sandbox=false) |
| Dirty git state | 1 (Analyze) | Warn, recommend commit/stash, pause for user decision |
| Already onboarded | 1 (Analyze) | Report current state, offer re-run if user suspects drift |
| kinfra not installed | 2 (Propose) | Error with instructions to run install.sh |
| kinfra init --dry-run fails | 2 (Propose) | Show error output, abort with explanation |
| Compose doesn't parse after changes | 4 (Verify) | Restore from .bak, report failure |
| OTEL config format not recognized | 2 (Propose) | Surface to user: "I found OTEL config at X but I'm not sure how to update it. Here's what I see — how should this change?" |
| User denies proposal | 2 (Propose) | Abort cleanly, no changes made |

## Integration Points

| Component | Current State | Change Needed |
|-----------|---------------|---------------|
| `init_cmd.py` | Interactive only (typer.prompt/confirm) | Add `--dry-run` and `--auto` flags |
| `init_command()` function | Returns exit code, writes directly | Refactor: extract detection into pure functions, add dry-run path |
| `install.sh` | Symlinks skills/ to tool dirs | Will pick up new skill automatically (no change needed) |
| `project.md` (target project) | May or may not have Infrastructure section | Skill adds/updates Infrastructure section in Phase 3 |

## Verification Approach

| Component | How to Verify |
|-----------|---------------|
| `--dry-run` flag | Unit test: runs detection, produces output, writes no files |
| `--auto` flag | Unit test: runs without stdin, uses defaults, produces same result as interactive with defaults accepted |
| `--dry-run --auto` combined | Unit test: produces preview output, writes nothing |
| SKILL.md | Manual: run `/kinfra-onboard` on khealth, verify phased flow |
| --check mode | Manual: run `/kinfra-onboard --check` on onboarded and non-onboarded projects |

## Implementation Planning Summary

### New Components to Create

| Component | Location | Purpose |
|-----------|----------|---------|
| kinfra-onboard skill | `skills/kinfra-onboard/SKILL.md` | Phased onboarding workflow instructions for Claude Code |

### Existing Components to Modify

| Component | Location | Changes Required |
|-----------|----------|------------------|
| init_cmd.py | `src/devops_ai/cli/init_cmd.py` | Add `--dry-run` and `--auto` flags to init_command(); refactor detection logic into reusable functions; add dry-run output formatting |
| main.py (CLI) | `src/devops_ai/cli/main.py` | Wire new flags through to init_command() |
| install.sh | `install.sh` | No change needed — auto-discovers skills/ |
