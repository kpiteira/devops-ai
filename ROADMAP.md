# devops-ai Roadmap

Last updated: 2026-08-24

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

### v0.4 — Quality Infrastructure Standard
- `kinfra init` generates quality artifacts: Justfile, Makefile, pre-commit hook, CI/security workflows, Claude hooks
- Graduated enforcement: Claude hooks (~2s lint), pre-commit (~30s quality+tests), CI (~2min full+AI review)
- Testing taxonomy rule (unit/integration/E2E classification)
- Pytest conftest guardrails block socket.connect in unit tests
- AI code review and security review in GitHub Actions
- Re-init preserves custom secrets, files, and env values
- 299 unit tests

### v0.5 — The Human–Model Contract (v2 rewrite)
- Contract doc landed (`docs/designs/v2-contract/CONTRACT.md`): rigid about outcomes, silent about paths
- Tasks removed from the framework — kplan deleted, kloop absorbed; path from brief to milestone is the executor's
- `/kspec` (planner: walkthrough, interview, spec + briefs + planner-authored acceptance tests, triage, replan, close) replaces `/kdesign`
- `/kbuild` rewritten thin (executor: one brief, goal loop on blocking tests, escape valve, milestone PR)
- Templates: `intent-spec.md`, `work-brief.md` (lint + escape valve baked in); amendment-flag and divergence mechanics specified
- Rules reconciled: `tdd` → `test-quality` (process mandate dropped, honesty bar kept), `handoffs` deleted (state lives in the spec + git), acceptance tests added to the taxonomy
- Evolutions backlog imported (`docs/EVOLUTIONS.md`)

## Backlog

### v2 remaining (CONTRACT.md next steps)

- [ ] **Validation pipeline** — new-public-symbol detection per PR; first architecture tests (contract steps 5)
- [ ] **PR gate wiring** — map `Milestone: M<N>` PR line to its acceptance-test run in CI
- [ ] **Pilot on one real feature** — measure interruptions, escalation quality, and run the adversarial test (fresh session tries to pass all blocking criteria while violating intent)
- [ ] **Post-pilot review** — did briefs stay outcome-only; did the right things escalate; re-teaching and re-litigation costs
- [ ] **Conformance ∘ e2e seam** — how intent review and the ke2e pipeline compose (EVOLUTIONS.md #2)
- [ ] **Code review process** — de-babysit PRs (EVOLUTIONS.md #3)
- [ ] **Roadmap grounding view** — always-current status aggregated from specs (EVOLUTIONS.md #4)

### Dogfooding

- [ ] **Test on agent-memory or khealth** — Validate skills on projects outside ktrdr/devops-ai. These projects have different stacks and will expose assumptions baked into the skills.

### Housekeeping

- [ ] **Archive old design docs** — `docs/designs/skill-generalization/` (v0.1) and `docs/designs/kinfra-kworktree/` (v0.2) are complete. Add status headers so future sessions don't confuse them with active work.
- [ ] **ktrdr migration decision** — ktrdr still uses its own commands. Now that devops-ai is validated, decide: migrate ktrdr to devops-ai skills, or keep separate?

### Skill Improvements

- [ ] **Agent teams prototype** — `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` enables parallel work within a milestone. Worth a spike for large milestones in `/kbuild`.
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
