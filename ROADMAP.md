# devops-ai Roadmap

Items captured during v0.1 development (M1-M4) for future consideration.

## Completed (v0.1)

- 5 portable skills: kdesign, kdesign-validate, kdesign-impl-plan, ktask, kmilestone
- Multi-tool install (Claude Code, Codex, Copilot + 10 more via Agent Skills standard)
- Graceful degradation (no-config, partial config, malformed config)
- Config generation from project inspection
- Shared E2E testing workflow
- Documentation and AGENTS.md

## Near-term: Battle Testing

- [ ] Use k* skills on agent-memory (first real project outside ktrdr)
- [ ] Capture friction points and awkward patterns from real usage
- [ ] Determine if ktrdr should migrate to devops-ai skills (currently deferred — ktrdr keeps its own commands until devops-ai is validated)

## Future: Skill Improvements

- [ ] **Skill size optimization** — kdesign-impl-plan is 974 lines (guidance is < 500). Move appendix/tables to `references/` directory if tools start enforcing limits
- [ ] **kissue skill** — Issue triage and implementation command (concept captured, not yet designed)
- [ ] **Validation CLI integration** — `skills-ref validate ./my-skill` exists in the Agent Skills ecosystem; could add to install script or CI
- [ ] **Progressive disclosure** — Use `references/`, `scripts/`, `assets/` directories per Agent Skills spec for large skills

## Future: Infrastructure (kinfra for new repos)

- [ ] **Worktree management** — `kinfra spec`, `kinfra impl`, `kinfra done` for any project
- [ ] **Sandbox system** — Isolated dev environments with port management
- [ ] **Test infrastructure** — Docker/compose orchestration per-project
- [ ] Decide: should this be a separate skill, a separate tool, or an extension of devops-ai?

## Future: Ecosystem

- [ ] **Test with Codex CLI and Copilot CLI** — Only tested on Claude Code so far
- [ ] **Test with broader tools** — Gemini CLI, Cursor, Amp, etc. all support Agent Skills
- [ ] **Codex description constraint** — Codex limits descriptions to 500 chars (vs spec's 1024). Verify our descriptions fit.
- [ ] **Community feedback** — Once stable, consider open-sourcing

## Non-Goals (Unchanged)

- Not building a plugin/extension system — config covers known variation
- Not building E2E agent infrastructure in devops-ai — skills have hooks for it, projects provide their own
