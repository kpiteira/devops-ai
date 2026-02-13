# devops-ai Roadmap

Last updated: 2026-02-13

## Completed

### v0.1 — Skill Generalization
- Ported 5 skills from ktrdr to devops-ai (kdesign, kdesign-validate, kdesign-impl-plan, ktask, kmilestone)
- Multi-tool install (Claude Code, Codex, Copilot via Agent Skills standard)
- Config system (`.devops-ai/project.md`) with graceful degradation
- Shared E2E testing workflow

### v0.2 — kinfra CLI (4 milestones)
- Git worktree management (spec/impl/done)
- Docker sandbox slots with port isolation and global registry
- Shared observability stack (Jaeger/Grafana/Prometheus on 4xxxx ports)
- Agent-deck integration with `--session` flag
- `/kinfra-onboard` skill for phased project onboarding
- 185 unit tests, 8 E2E tests

### v0.3 — Skills Modernization for Opus 4.6
- Extracted 6 shared rules to `.claude/rules/` (~1,490 tokens always-on)
- Merged 10 skills → 7: kdesign+kdesign-validate → `/kdesign`, kdesign-impl-plan → `/kplan`, ktask+kmilestone → `/kbuild`
- 4,194 → 1,195 lines (71% reduction)
- Shifted from prescriptive recipes to principled briefs
- Added kreview and kissue skills
- install.sh gains stale cleanup, rules distribution, `--rules` flag

## Backlog

### Dogfooding

- [ ] **Use modernized skills on a real feature** — Run `/kdesign` → `/kplan` → `/kbuild` end-to-end on the next real piece of work. Capture friction points: what's missing, what's confusing, what triggers poorly.
- [ ] **Test on agent-memory or khealth** — Validate skills on projects outside ktrdr/devops-ai. These projects have different stacks and will expose assumptions baked into the skills.

### Housekeeping

- [ ] **Archive old design docs** — `docs/designs/skill-generalization/` (v0.1) and `docs/designs/kinfra-kworktree/` (v0.2) are complete. Add status headers so future sessions don't confuse them with active work.
- [ ] **ktrdr migration decision** — ktrdr still uses its own commands. Now that devops-ai is validated, decide: migrate ktrdr to devops-ai skills, or keep separate?

### Skill Improvements

- [ ] **Agent teams prototype** — `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` enables parallel work within a milestone (one agent implements task N, another writes tests for task N+1). Worth a spike to see if it speeds up `/kbuild` on large milestones.
- [ ] **Skill frontmatter features** — Claude Code supports `context: fork` (run skill in isolated subagent), `model:` (per-skill model selection), and dynamic context via `!command` syntax. Evaluate which would improve skill behavior.
- [ ] **Path-scoped rules** — `.claude/rules/` supports path globs in frontmatter. Could be useful for project-specific patterns (e.g., test conventions scoped to `tests/**/*.py`). Probably not needed for universal principles.

### Ecosystem

- [ ] **Test with Codex CLI and Copilot CLI** — Skills are symlinked to all three tools but only tested with Claude Code. Verify they work or degrade gracefully.
- [ ] **Codex description constraint** — Codex limits skill descriptions to 500 chars (vs spec's 1024). Verify ours fit; truncate if needed.
- [ ] **Skill validation in CI** — Agent Skills ecosystem has `skills-ref validate ./my-skill`. Could add to install script or CI to catch malformed skills early.

## Non-Goals

- Not building a plugin/extension system — config covers known variation
- Not building E2E agent infrastructure in devops-ai — skills have hooks for it, projects provide their own
- Not targeting ktrdr migration until devops-ai skills are battle-tested on 2+ other projects
