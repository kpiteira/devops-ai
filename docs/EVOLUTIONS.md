# devops-ai — Evolutions Backlog

*A running log of framework evolutions we intend to make. Each entry states the problem before the solution, so entries stay meaningful over time.*

## 1. Human–model contract rewrite (in design)

**Problem:** the kdesign/kplan/kbuild framework prescribes process, which caps frontier models at the human's plan and wastes their planning/verification abilities.
**Direction:** outcome-only intent specs and work briefs, executor agency with an escape valve, anti-deference escalation protocol, comprehension layer (glossary, architecture-as-tests, event-triggered interrogation).
**Status:** design doc validated by two independent cold-reader comprehension probes (transport mechanics deferred by design, semantics confirmed unambiguous). Ready for the Claude Code working session.

## 2. Conformance & e2e validation integration

**Problem:** the new Fable conformance review covers intent conformance and architectural coherence only; functional e2e validation (as devops-ai does today) must stay, and the two need a clean seam.
**Direction:** define how the intent-level review and the e2e pipeline compose — ordering, shared artifacts (briefs' acceptance criteria as e2e seeds?), what blocks a feature boundary.
**Status:** identified during contract-rewrite review; deliberately kept out of the contract doc's scope.

## 3. Code review process ("babysitting PRs")

**Problem:** PR review currently demands ongoing human attention, and per the new contract, human PR-reading neither catches the failures that matter (cross-PR inconsistency) nor is a good use of energy.
**Direction:** to be designed — likely builds on the Pi validator-agent architecture and the conformance review, with the human involved only at escalation.
**Status:** not started.

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
