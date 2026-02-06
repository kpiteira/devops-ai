# Skill Generalization: Design

## Problem Statement

We have five battle-tested development workflow commands (kdesign, kdesign-validate, kdesign-impl-plan, kmilestone, ktask) that encode valuable patterns: collaborative design, scenario validation, vertical milestones, TDD execution, and handoff continuity. These patterns are project-agnostic, but the commands are hardcoded to ktrdr (make targets, docker compose, e2e agent system, specific paths). We need to extract the portable core, make it configuration-driven, and package it as versioned, installable skills that any project gets out of the box — with ktrdr eventually migrating to use the generalized versions.

## Goals

1. **Extract portable core** — Separate universal workflow patterns from project-specific tooling
2. **Configuration-driven** — Projects provide a markdown prompt with their test commands, infrastructure, paths; skills adapt
3. **Versioned and installable** — Skills live in this repo, symlinked to tool directories, updates propagate via git pull
4. **Preserve what works** — The ktrdr commands are proven. Don't lose their effectiveness in the abstraction
5. **AGENTS.md support** — Provide templates using the industry-standard naming
6. **Cross-tool portable** — Skills follow the Agent Skills standard, working with Claude Code, Codex CLI, and GitHub Copilot CLI

## Non-Goals (Out of Scope)

1. **Not replacing ktrdr's commands now** — ktrdr migrates when devops-ai is ready, not before
2. **Not building E2E agent infrastructure in v1** — E2E is a future capability; skills should have a hook for it but not require it
3. **Not building a plugin/extension system** — Configuration covers known variation points; extensibility can come later
4. **Not building a CLI tool** — Installation is a simple script, not a framework

## User Experience

### Scenario 1: New Project Setup

Karl creates a new Python project. He has devops-ai cloned and installed (symlinks exist). In the new project, he copies the config template:

```bash
mkdir -p .devops-ai
cp ~/Documents/dev/devops-ai/templates/project-config.md .devops-ai/project.md
```

He edits `.devops-ai/project.md` with project-specific values (test commands, paths). Now `/kdesign`, `/ktask`, `/kmilestone` all work, adapted to this project.

### Scenario 2: Existing Project with Docker + E2E

A more complex project (like ktrdr) has a richer config prompt describing Docker infrastructure, e2e agents, sandbox system, and custom test patterns. The same k* commands adapt to this richer environment.

### Scenario 3: Running /kdesign

Karl types `/kdesign feature: Add persistent memory retrieval`. The skill reads `.devops-ai/project.md`, discovers the project context, and runs the standard design workflow — problem exploration, options, pauses, design doc, architecture doc — saving to the configured designs path.

### Scenario 4: Running /ktask with TDD

Karl types `/ktask M1_core.md 1.2`. The skill reads project config, knows to use `uv run pytest tests/unit` instead of `make test-unit`, knows there's no docker infrastructure, and runs the standard TDD cycle: RED → GREEN → REFACTOR.

### Scenario 5: No Config Yet

Karl tries `/kdesign` in a project without `.devops-ai/project.md`. The skill notices the missing config and asks for essential values (test command, quality command) before proceeding. It suggests creating a config file for next time.

## Key Decisions

### Decision 1: Keep the k prefix
**Choice:** Keep `/kdesign`, `/kdesign-validate`, `/kdesign-impl-plan`, `/kmilestone`, `/ktask`
**Alternatives:** Drop prefix; use different prefix
**Rationale:** The `k` is ours. It's identity.

### Decision 2: Project config as a markdown prompt
**Choice:** `.devops-ai/project.md` — a tool-agnostic markdown prompt loaded by every k* command as its first step
**Alternatives:** YAML config file; `.claude/config/project.md` (tool-specific); frontmatter in AGENTS.md; auto-detection from package.json/pyproject.toml
**Rationale:** Skills are prompts. Config as a prompt composes naturally — no parsing, no special handling. The command reads a .md file and adapts. The config belongs to devops-ai, not to any particular tool — `.devops-ai/` makes it tool-agnostic.

### Decision 3: Installation via symlinks
**Choice:** A shell script that symlinks `devops-ai/skills/*/` → each tool's skills directory (`~/.claude/skills/`, `~/.codex/skills/`, `~/.copilot/skills/`)
**Alternatives:** Copy-based install; package manager; manual setup; dual-install to commands/ and skills/
**Rationale:** Symlinks mean `git pull` on devops-ai automatically updates all skills across all tools. All tools use the same `skills/` path pattern following the Agent Skills standard. Simple, no dependencies.

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

### Decision 7: Agent Skills standard for cross-tool portability
**Choice:** Skills follow the open [Agent Skills specification](https://agentskills.io) — directory-based structure (`skill-name/SKILL.md`) with YAML frontmatter
**Alternatives:** Claude Code-only flat files; custom format per tool; lowest-common-denominator plain text
**Rationale:** The Agent Skills standard is adopted by Claude Code, Codex CLI, GitHub Copilot CLI, Cursor, and others. Following it means skills work across tools without custom adapters. The install script handles symlinking to each tool's expected location.

### Decision 8: E2E content extracted to separate prompt
**Choice:** E2E testing instructions extracted from ktask/kmilestone into a separate prompt file, loaded conditionally when E2E is configured
**Alternatives:** Keep inline with conditional markers; remove E2E entirely for v0
**Rationale:** E2E content is ~150 lines per skill. Extracting it keeps the base skills focused while preserving full E2E capability for projects that need it.

## Open Questions

1. ~~**Project-specific skill extensions**~~ — **RESOLVED:** Handled via "Project-Specific Patterns" section in config prompt. ktrdr's CLI test patterns (runner fixture, ANSI codes) go in its project.md config.

2. ~~**Skill interdependencies**~~ — **RESOLVED:** Cross-skill references are text-only ("Run /kdesign-validate"). E2E content extracted to separate prompt file loaded conditionally. Skills degrade gracefully when referenced capabilities aren't available.

3. ~~**How to handle the existing ktrdr commands**~~ — **RESOLVED (deferred):** ktrdr keeps its own commands until devops-ai is validated. Migration approach to be determined when ready.

4. ~~**Agent Skills token limits**~~ — **RESOLVED:** < 5000 tokens / < 500 lines is a recommendation, not a hard limit. Use `references/` directory for overflow. See `research/agent-skills-research.md`.

5. ~~**Claude Code skill discovery**~~ — **RESOLVED:** Confirmed. `name` field → slash command. `~/.claude/skills/kdesign/SKILL.md` with `name: kdesign` → `/kdesign` works.

6. ~~**Codex/Copilot skill paths**~~ — **RESOLVED:** Codex: `~/.codex/skills/`. Copilot: `~/.copilot/skills/` (also reads `~/.claude/skills/` for cross-compat). All follow `~/.<tool>/skills/<name>/SKILL.md`.
