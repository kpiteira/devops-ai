# Skill Generalization: Design

## Problem Statement

We have five battle-tested development workflow commands (kdesign, kdesign-validate, kdesign-impl-plan, kmilestone, ktask) that encode valuable patterns: collaborative design, scenario validation, vertical milestones, TDD execution, and handoff continuity. These patterns are project-agnostic, but the commands are hardcoded to ktrdr (make targets, docker compose, e2e agent system, specific paths). We need to extract the portable core, make it configuration-driven, and package it as versioned, installable skills that any project gets out of the box — with ktrdr eventually migrating to use the generalized versions.

## Goals

1. **Extract portable core** — Separate universal workflow patterns from project-specific tooling
2. **Configuration-driven** — Projects provide a markdown prompt with their test commands, infrastructure, paths; skills adapt
3. **Versioned and installable** — Skills live in this repo, symlinked to `~/.claude/commands/`, updates propagate via git pull
4. **Preserve what works** — The ktrdr commands are proven. Don't lose their effectiveness in the abstraction
5. **AGENTS.md support** — Provide templates using the industry-standard naming

## Non-Goals (Out of Scope)

1. **Not replacing ktrdr's commands now** — ktrdr migrates when devops-ai is ready, not before
2. **Not building E2E agent infrastructure in v1** — E2E is a future capability; skills should have a hook for it but not require it
3. **Not building a plugin/extension system** — Configuration covers known variation points; extensibility can come later
4. **Not building a CLI tool** — Installation is a simple script, not a framework

## User Experience

### Scenario 1: New Project Setup

Karl creates a new Python project. He has devops-ai cloned and installed (symlinks exist). In the new project, he copies the config template:

```bash
mkdir -p .claude/config
cp ~/Documents/dev/devops-ai/templates/project-config.md .claude/config/project.md
```

He edits `.claude/config/project.md` with project-specific values (test commands, paths). Now `/kdesign`, `/ktask`, `/kmilestone` all work, adapted to this project.

### Scenario 2: Existing Project with Docker + E2E

A more complex project (like ktrdr) has a richer config prompt describing Docker infrastructure, e2e agents, sandbox system, and custom test patterns. The same k* commands adapt to this richer environment.

### Scenario 3: Running /kdesign

Karl types `/kdesign feature: Add persistent memory retrieval`. The skill reads `.claude/config/project.md`, discovers the project context, and runs the standard design workflow — problem exploration, options, pauses, design doc, architecture doc — saving to the configured designs path.

### Scenario 4: Running /ktask with TDD

Karl types `/ktask M1_core.md 1.2`. The skill reads project config, knows to use `uv run pytest tests/unit` instead of `make test-unit`, knows there's no docker infrastructure, and runs the standard TDD cycle: RED → GREEN → REFACTOR.

### Scenario 5: No Config Yet

Karl tries `/kdesign` in a project without `.claude/config/project.md`. The skill notices the missing config and asks for essential values (test command, quality command) before proceeding. It suggests creating a config file for next time.

## Key Decisions

### Decision 1: Keep the k prefix
**Choice:** Keep `/kdesign`, `/kdesign-validate`, `/kdesign-impl-plan`, `/kmilestone`, `/ktask`
**Alternatives:** Drop prefix; use different prefix
**Rationale:** The `k` is ours. It's identity.

### Decision 2: Project config as a markdown prompt
**Choice:** `.claude/config/project.md` — a markdown prompt loaded by every k* command as its first step
**Alternatives:** YAML config file; frontmatter in AGENTS.md; auto-detection from package.json/pyproject.toml
**Rationale:** Skills are prompts. Config as a prompt composes naturally — no parsing, no special handling. The command reads a .md file and adapts. This is the simplest thing that works.

### Decision 3: Installation via symlinks
**Choice:** A shell script that symlinks `devops-ai/skills/*.md` → `~/.claude/commands/*.md`
**Alternatives:** Copy-based install; package manager; manual setup
**Rationale:** Symlinks mean `git pull` on devops-ai automatically updates all skills. Simple, no dependencies.

### Decision 4: Graceful degradation without config
**Choice:** Skills work without config by prompting for needed values; config makes it automatic
**Alternatives:** Hard-fail without config; use defaults only
**Rationale:** A new project shouldn't be blocked from using `/kdesign` just because config isn't set up. The skill asks what it needs.

### Decision 5: Conditional sections for optional capabilities
**Choice:** Skills include all sections but clearly mark optional ones ("If e2e is configured...", "If infrastructure exists...")
**Alternatives:** Separate skill variants per capability level; template-generated skills
**Rationale:** Single source files are maintainable. The skill tells Claude to skip sections when capability isn't configured.

### Decision 6: Templates provided
**Choice:** devops-ai provides templates for:
- `project-config.md` (project configuration prompt)
- `AGENTS.md` (project instructions, industry standard)
**Rationale:** Quick project bootstrap. Copy template, fill in values, done.

## Open Questions

1. **Project-specific skill extensions** — e.g., ktrdr has CLI test patterns (runner fixture, ANSI codes). Should there be a mechanism for project-local additions to skills, or does the config prompt handle this via a "Project-Specific Patterns" section?

2. **Skill interdependencies** — kdesign-impl-plan references kdesign-validate, ktask references e2e agents. How do we handle cross-skill references when some capabilities aren't available?

3. **How to handle the existing ktrdr commands** — When ktrdr migrates, do we delete its `.claude/commands/` and rely on the symlinked globals? Or keep project-local overrides?
