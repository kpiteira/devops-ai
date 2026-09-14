# devops-ai Roadmap

Last updated: 2026-09-14

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
- Rules reconciled: `tdd` → `test-quality` (process mandate dropped, honesty bar kept), `handoffs` deleted (state lives in the spec + git), acceptance tests added to the taxonomy; `outcome-contracts` rule states the contract core in every session
- Enforcement (merged from the parallel Copilot proposal): `kinfra init` generates a contract-integrity guard (briefs + acceptance tests writable only on `spec/*`/`replan/*`, run from the PR base commit so a PR can't neuter it) and a new-public-symbol signal; `tests/architecture/test_v2_contract.py` gates the framework's own contract surfaces
- Evolutions backlog imported (`docs/EVOLUTIONS.md`)

### v0.6 — Pilot, synthesis, and the review loop
- v2 contract piloted end to end on khealth "challenges" (2026-09-01 → 09-11, `docs/designs/v2-contract/PILOT.md`), synthesised in `REVIEW.md`; contract, rules, skills and templates revised to v7 (PR #27); decisions T1–T5 signed in `docs/specs/v2-pilot-synthesis/SPEC.md`
- `kobserve` observer seat: independent verification and the *For the human* gate before a milestone merges (PR #27)
- Review loop redesigned on the data from two runaway loops (issue #33): written `## Review scope` required, OUT OF SCOPE disposition files issues, computed finding provenance, second-order stop, stopping as a state, push-back ratio reported (#34); a rebase resets the provenance boundary (#41); `kselfreview` moved into the repo (#39, #42); `kbabysit` runs forked on Opus via skill frontmatter, gated by the architecture tests (#45)
- `secret-providers` M1 delivered: `ksecret` console script resolving `$VAR`/`env://`, `dotenv://` and `op://` references, kinfra `[sandbox.secrets]` on the same resolver (`docs/specs/secret-providers/`, PR #32)
- CodeQL and Dependabot backlog cleared with reasons on every alert (#38, #43); integration tests skip instead of fail without Docker (#44)
- Housekeeping: personal references out of skills (#47), tool-artifact lines out of docs (#48)

## Backlog

### v2 remaining (CONTRACT.md next steps)

- [ ] **PR gate wiring** — run a milestone PR's own `blocking:` command as a *separate, selectively-triggered* workflow (ready-for-review + manual re-trigger, required at merge). Never in the standing `check` job: that job stays unit-only under the 2-minute CI budget (EVOLUTIONS.md #5). Needs the per-project can-CI-run-the-stack answer; today the goal loop and the executor's PR evidence carry it
- [ ] **Required checks on main** (#28) — devops-ai's ruleset is live since 2026-09-14: pull request required, `check` + `integration` required (not strict — parallel executors), no bypass; spec bookkeeping rides the milestone PR (`kobserve`). Remaining: `kinfra init` prints the one-time instruction and generates a CODEOWNERS entry for the guard and the workflow
- [ ] **Conformance ∘ e2e seam** — how intent review and the ke2e pipeline compose (EVOLUTIONS.md #2)
- [ ] **Roadmap grounding view** — always-current status aggregated from specs (EVOLUTIONS.md #4); this file is still hand-maintained
- [ ] **Review loop, second pilot** — first milestone PRs under the redesigned loop ran 2026-09-13: #51 (M2) stopped second-order at round 2, 5 of 6 findings implemented, 1 pushed back; #49 (M3) stopped on the round budget without converging, 5 of 6 implemented, 1 filed out of scope (#52). Reading those two reports against the runaway-loop data is the measurement (EVOLUTIONS.md #3)

### secret-providers (in flight)

- [ ] **M2 — OpenBao provider** (`bao://`, PR #51) and **M3 — Azure Key Vault provider** (`akv://`, PR #49), running in parallel on their own executor sessions
- [ ] **M4 — write** (optional, after M2 and M3)
- [ ] **Machine-credential provisioning** (in-container) — flagged for a later discussion at M1 sign-off

### Dogfooding

- [ ] **Test on agent-memory or khealth** — Validate skills on projects outside ktrdr/devops-ai. These projects have different stacks and will expose assumptions baked into the skills.

### Housekeeping

- [ ] **Archive old design docs** — `docs/designs/skill-generalization/` (v0.1) and `docs/designs/kinfra-kworktree/` (v0.2) are complete. Add status headers so future sessions don't confuse them with active work.
- [ ] **ktrdr migration decision** — ktrdr still uses its own commands. Now that devops-ai is validated, decide: migrate ktrdr to devops-ai skills, or keep separate?
- [ ] **Slot registry claim identity** (#31) — deferred 2026-09-13, not a priority: needs a brief with planner-authored race tests when picked up

### kinfra, on demand

Carried from #17 (closed 2026-09-13); both wait on a second onboarded project to be the consumer.

- [ ] **Health gate cascade** — ordered dependent health checks in `infra.toml`, so partial startup failures surface instead of passing a single endpoint probe
- [ ] **Local-prod pattern** — a non-worktree, non-slotted environment for projects with host service dependencies (GPU, native binaries, hardware)

### Skill Improvements

- [ ] **Agent teams prototype** — `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` enables parallel work within a milestone. Worth a spike for large milestones in `/kbuild`.
- [ ] **Skill frontmatter features** — `context: fork` + `model:` are in use since #45 (`kbabysit`); `rules/effort-and-model-calibration.md` records the fields. Still unevaluated: `effort:` per skill, and dynamic context via `!command` syntax.
- [ ] **Path-scoped rules** — `.claude/rules/` supports path globs in frontmatter. Could be useful for project-specific patterns (e.g., test conventions scoped to `tests/**/*.py`). Probably not needed for universal principles.

### Ecosystem

- [ ] **Test with Codex CLI and Copilot CLI** — Skills are symlinked to all three tools but only tested with Claude Code. Verify they work or degrade gracefully.
- [ ] **Codex description constraint** — Codex limits skill descriptions to 500 chars (vs spec's 1024). Verify ours fit; truncate if needed.
- [ ] **Skill validation in CI** — Agent Skills ecosystem has `skills-ref validate ./my-skill`. Could add to install script or CI to catch malformed skills early.

## Non-Goals

- Not building a plugin/extension system — config covers known variation
- Not building E2E agent infrastructure in devops-ai — skills have hooks for it, projects provide their own
- Not targeting ktrdr migration until devops-ai skills are battle-tested on 2+ other projects
