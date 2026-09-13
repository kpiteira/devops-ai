# devops-ai — Evolutions Backlog

*A running log of framework evolutions we intend to make. Each entry states the problem before the solution, so entries stay meaningful over time.*

## 1. Human–model contract rewrite (in design)

**Problem:** the kdesign/kplan/kbuild framework prescribes process, which caps frontier models at the human's plan and wastes their planning/verification abilities.
**Direction:** outcome-only intent specs and work briefs, executor agency with an escape valve, anti-deference escalation protocol, comprehension layer (glossary, architecture-as-tests, event-triggered interrogation).
**Status:** v6 piloted end to end on khealth "challenges" (2026-09-01 → 09-11, `docs/designs/v2-contract/PILOT.md`); synthesised in `REVIEW.md`; contract, rules, skills and templates revised to v7 (September 2026). Next: a second pilot on a different product, watching what v7 introduced.

## 2. Conformance & e2e validation integration

**Problem:** the new Fable conformance review covers intent conformance and architectural coherence only; functional e2e validation (as devops-ai does today) must stay, and the two need a clean seam.
**Direction:** define how the intent-level review and the e2e pipeline compose — ordering, shared artifacts (briefs' acceptance criteria as e2e seeds?), what blocks a feature boundary.
**Status:** identified during contract-rewrite review; deliberately kept out of the contract doc's scope.

## 3. Code review process ("babysitting PRs")

**Problem:** PR review currently demands ongoing human attention, and per the new contract, human PR-reading neither catches the failures that matter (cross-PR inconsistency) nor is a good use of energy.
**Direction:** to be designed — likely builds on the Pi validator-agent architecture and the conformance review, with the human involved only at escalation.
**Status:** first concrete step landed 2026-09-12 (devops-ai #34, data in #33): the babysit loop now requires a written `## Review scope` in the PR body, kreview has an OUT OF SCOPE disposition (true but not this PR's → issue), every finding carries a computed provenance (original diff / review-fix commit / unknown; the boundary is the earliest review still in the branch's history, so a rebase resets it at the cost of at most one extra round), and a round whose findings all sit on fix commits is the last one. Six criteria signed by Karl item by item; the pilot data (13- and 11-round loops) is in #33. Also landed 2026-09-12 (#25): the loop runs **forked on an Opus-grade model**, never inline on the invoking session's tier — `skills/kbabysit/SKILL.md` frontmatter carries `context: fork`, `agent: general-purpose`, `background: false` and `model: claude-opus-5` ([skill frontmatter reference](https://code.claude.com/docs/en/skills.md)), for tier economics (polling plus bounded judgement doesn't warrant top-tier tokens) and context hygiene (poll/CI/review output stays out of the invoking session). The fork sees no conversation history, so the skill body carries `$ARGUMENTS` and resolves the PR from the checkout; `kreview` runs inside that subagent, unforked. The human-at-escalation design above is still open.

## 4. Roadmap representation & grounding

**Problem:** running multiple teams of agents in parallel creates a heavy context-switch tax; the human needs a way to ground quickly at any moment — where each product stands, what's on deck short-term and long-term.
**Direction:** to be designed — a maintained, always-current roadmap view aggregating feature specs' status across products; possibly generated from the specs themselves so it can't drift from reality.
**Status:** not started.

## 5. CI budget and gate events

**Problem:** the always-run CI job must stay under 2 minutes (hard limit; ideally under 1) — the human's principle, and why it runs unit tests only. The milestone blocking gate is E2E and cannot live there; running it on every push would also be overly expensive.
**Direction:** blocking acceptance tests run as a separate, selectively-triggered workflow — on PR ready-for-review plus a manual re-trigger, required at merge — never in the standing `check` job. Needs per-project infra answers (can this project's stack stand up in a runner at all?).
**Status:** principle agreed 2026-08-30; wiring deferred to its own feature (see roadmap "PR gate wiring").

## 6. kinfra beyond Python containers

**Problem:** kinfra grew up on Python apps in Docker; the quality generation (uv-flavored Makefile, pytest conftest guardrails) is Python-centric with a thinner Node path, and the human is expanding beyond that world.
**Direction:** to be designed — keep the language-agnostic core (worktrees, slots, ports, compose, observability, guards) and make the quality layer pluggable per stack rather than grown by special cases.
**Status:** identified 2026-08-30, not started.
