# karchitect audit — design

**Status:** design in progress · **input:** `../architect-skill/DISTILLATION.md` · **v1 reference:** commit `1fdc2c9`

## Problem

Most projects have no honest, current description of how they're actually built — which makes them
hard to understand, risky to refactor, and easy to let rot further. The audit closes that gap:
point it at an existing codebase and get back **two things** —

1. **The map** — a factual description of how the system is *actually* structured.
2. **The findings** — a prioritized, evidence-backed list of its architectural problems.

The map serves understanding (and feeds "stay clean"); the findings feed refactoring ("get clean").

## Goals

- A map that is **progressive** (high-level first, drill down to any depth) and **complete** (every
  file accounted for), so it's neither a useless box diagram nor an unreadable octopus.
- Findings that are **real, evidenced, and actionable** — each tied to a consequence worth fixing.
- A **confidence signal** on both, so claims can be trusted without re-verification.
- **Honesty** about uncertainty and about what was not analyzed.
- Works on **real codebases** (agent-memory at 24K LOC, larger later), not toy projects.

## Non-goals

- **Not the refactor itself.** The audit is diagnostic. Turning findings into a sequenced refactor
  plan and executing it is "get clean" (`/kdesign` brief → `/kplan` → `/kbuild`).
- **Not lint/style.** Mechanical problems a linter can see (cross-file duplication, layering
  violations) belong in the always-on quality gates, not a periodic audit.
- **Not doc-authoring discipline.** Keeping the map current as code changes is "stay clean"
  (kbuild's Architecture Reconciliation), not this skill.
- **Not multi-language on day one.** Target Python first (where the dogfood projects live).

## Jobs to be done

- **J1 — the map.** When I open a project with no up-to-date architecture doc, I want a factual map
  of how it's actually structured, so I understand the system in minutes instead of reading all of it.
- **J2 — refactor targets.** When I'm about to clean up a messy codebase, I want a prioritized list
  of its real architectural problems, each pinned to specific code, so I can scope the refactor.
- **J3 — confidence.** When the audit tells me something, I want to know how much to trust it (did
  independent passes agree?), so I don't re-verify its claims by hand.
- **J4 — honesty.** When I read the audit, I want it upfront about what it's unsure of, where passes
  disagreed, and what it didn't analyze, so confident-sounding but shaky conclusions don't mislead me.
- **J5 — freshness.** When code has changed since the last audit, I want a current map without
  redoing it by hand, so the description doesn't quietly go stale.
- **J6 — scale.** When I point it at a big real project, I want it to actually work at that size.
- **J7 — feeds the pipeline.** When an agent runs the audit inside a bigger job, I want structured
  outputs it can consume, so findings flow into `/kdesign`/`/kplan` without a human re-typing them.
- **J8 — exhaustive coverage.** When I trust the map, I want *every* file examined and accounted for
  (not sampled), so there are no blind spots. (Examined and classified — not every file is a map node.)

## Key decisions (and why)

1. **Build the map bottom-up from code.** Break down every file → cluster into components →
   synthesize the high-level view *from the breakdowns*. *Why:* cross-cutting problems (scattered
   access, inconsistent abstraction) only appear when you can see the whole system — which a sample
   never can. The breakdowns are also a **compression layer** that lets the synthesis see the whole
   system at once (where Opus 4.8's large context window earns its keep). To make cross-cutting
   findings detectable, each breakdown records **structured dependency/access edges** (imports,
   calls, state read/written — each with a site), not prose — so the aggregate is a queryable graph
   where "writes in 40 places" or "Claude Code hardcoded here, abstracted there" shows up as a
   pattern even when no single file looks wrong in isolation. This is what makes the bottom-up bet
   work; without it, cross-cutting findings have no evidence.
2. **Code is the sole source of truth — for now.** The map is derived from code only; docs never
   feed it. *Why:* docs are stale. Build the map from code *first, unanchored*, then compare to docs
   on a separate pass — every drift resolves as "code is truth, doc is stale." (Stated assumption,
   not permanent law: once "stay clean" keeps docs current, they earn back authority.)
3. **Exhaustive coverage via classification.** Every file is examined and bucketed: **source** (full
   breakdown, feeds the map) · **tests** (mapped to what they verify; a coverage view + a finding
   source) · **docs** (claims checked against code on the drift pass) · **config/build/CI** (the
   "how it's built and run" view) · **generated/vendored/fixtures** (acknowledged and set aside —
   *and the audit says so*). *Why:* "no blind spots" without bloating the map (fights the octopus).
4. **Progressive zoom = the build layers.** high-level map → components → file breakdowns. Every
   level is backed by the one below, down to real files. *Why:* one artifact, many depths.
5. **Confidence at the synthesis level.** Multiple agents independently synthesize the high-level map
   and agree (or don't); each file is broken down once. *Why:* agreement on "what the system is" is
   what you need to trust; double-reading every file multiplies cost for little gain. Critical files
   can be cross-read selectively.
6. **Two modes.** **Full** (first run): exhaustive, expensive, optimized for completeness — a
   one-time investment. **Refresh** (stay green): only changed files re-broken-down, map
   re-synthesized. *Why:* the cost is a one-time bill; afterward it's incremental.
7. **Findings are diagnostic and ratifiable.** Each carries: the **problem** (stated as a problem,
   not a fact) · the **consequence** (what it blocks or risks — what makes it a target, not a
   nitpick) · **evidence** (site or list of sites) · **confidence** (independent agreement) ·
   **draft severity** (blast-radius × risk — no formal taxonomy) · **status** (you ratify; can mark
   `wont-fix`). *Why:* the map is factual; findings are judgment, and judgment can be wrong.
8. **Clean boundaries.** Audit = diagnosis (map + flat findings). Clustering findings into refactor
   *themes* with a sequence = the first step of "get clean." Lint-catchable problems = quality gates.
9. **Components: single membership, with a kind.** Each file belongs to exactly one component (clean
   partition; stable identity for refresh/repro). Components are tagged *feature* or
   *shared/foundational*. *Why:* a file that genuinely belongs to two *feature* components is usually
   a smell — forcing single membership makes that strain visible as a **coupling finding** rather
   than smoothing it over. The *shared* kind keeps genuinely cross-cutting infrastructure (utils,
   base types, the one gateway) from being mislabeled as a problem. The model strains against messy
   reality and *reports where it strains*.

## Implementation-readiness — the shapes that will calcify

These are the data shapes everything else is built on; worth pinning before building (settled in
ARCHITECTURE.md):

- **File-breakdown record** — the atom. Fields: path · classification · one-line responsibility ·
  **structured edges** (imports / calls / reads_state / writes_state, each with a site) · problems
  noticed (with citation). The edges are the cross-cutting-finding substrate (decision 1).
- **Finding record** — id · title · **category** · problem · consequence · evidence-sites[] ·
  confidence · severity · status. Dedup key for merging across synthesizers = category + overlapping
  sites.
- **Component identity across runs** — a component keeps a stable identity so refresh (J5) and the
  reproducibility check (J3) work: a canonical name + its set of member files + its kind
  (feature/shared); "the same" across runs if its file-set overlaps >threshold.
- **Artifact location** — in the *target* repo under `docs/architecture/audit/<ISO-timestamp>/`.

## Milestones (proposed — react)

Vertical slices; each runs end-to-end on agent-memory and is validated against its known problems.

- **M1 — the core loop, top level only.** Break down every source file → synthesize the *high-level*
  map + the cross-cutting findings. No drill-down levels, no drift pass, no refresh. **Validates the
  central bet.** Done when: you read the high-level map in ~5 min and recognize agent-memory; the
  findings include the known ones (the `services.py` god-module, scattered access); independent
  synthesizers' agreement is reported. (Compare against the preserved v1 run as a baseline.)
- **M2 — progressive depth + full classification.** Add the drill-down levels (components → files)
  and the full file-classification (tests/docs/config/generated handled per §3). Delivers J1's
  "progressive" and J8's "complete." Done when: every file is accounted for, and you can zoom from
  the top to any file.
- **M3 — the drift pass + confidence surfacing.** Compare docs against the code-derived map to
  produce drift findings; surface the confidence/disagreement signal in the output (J4). Done when:
  a known stale-doc claim shows up as a drift finding.
- **M4 — refresh mode (stay green).** Re-run touching only changed files; update the map and
  findings incrementally (J5). Done when: a small code change refreshes the map without a full re-run.

**Scale (J6)** is exercised throughout (agent-memory is the M1 target), not deferred to its own
milestone — if the core loop can't handle 24K LOC, we want to know at M1.
</content>
