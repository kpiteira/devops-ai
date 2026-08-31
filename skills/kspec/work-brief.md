---
feature: <feature-slug>
milestone: M<N>
spec: ../SPEC.md
blocking: <exact scoped command — exits 0 only when every job below is satisfied>
---

<!--
WORK BRIEF — one per milestone, at docs/specs/<feature>/briefs/M<N>-<slug>.md.
This document plus the current code is an executor session's ENTIRE context — it does
not need, and does not get, the planning conversation. Write it for a stranger.

The spec's lint applies here too: facts, decisions, testable end states, labeled
directives. An unlabeled process instruction is a bug in the brief.

Milestone status lives in the spec's Decomposition table, not here. The `blocking:`
frontmatter is machine-read (PR gate, goal loop); keep it exact.
-->

# Brief <N> — <Milestone name>

## Jobs

<!-- One or more JTBDs: *When [situation], [who] can [job], so that [value].*
Every job maps to at least one blocking acceptance test — a job with no test is an
aspiration, not a contract; a test with no job is process leaking back in. -->

- **J1** — When <situation>, <who> can <job>, so that <value>.

## Surface

<!-- The observable surface the acceptance tests exercise, pinned at planning time:
the CLI command, HTTP route, file format, UI flow. The tests are unwritable without
this — and the surface IS the outcome; everything behind it is the executor's. -->

## Blocking

<!-- Planner-authored acceptance tests, committed at planning time, before any
implementation exists. Delivered means the command above exits 0. Scoped runs, not
general-CI members: they run in the executor's goal loop and as a gate on this
milestone's PR, nowhere else. -->

| Job | Planner-authored test | Observable proof |
|-----|-----------------------|------------------|
| J1 | `tests/acceptance/<feature>/test_m<N>_<slug>.py::test_<job>` | <what a passing assertion proves> |

Plus the standing gates: `make check` exits 0.

## Advisory

<!-- Worth attempting, never worth burning a session on. -->

## Invariants

<!-- What this milestone must not change. -->

## Non-goals

## Context

<!-- What the planner knows that the executor won't cheaply rediscover — adjacent
features sharing this state, the job that reads the same query helper, the reason
an odd-looking thing is load-bearing. -->

## Decisions

<!-- Contained, reversible choices the planner made — challengeable by the executor
through the escape valve. A path the HUMAN prescribes is labeled:
**Directive — human:** <path, and the reason outside the codebase>. -->

---

**If a stated fact is false, a decision conflicts with what's actually in the codebase,
or an acceptance test contradicts a job: stop and describe what you found. Don't comply,
and don't classify the problem yourself.**

<!-- The escape valve, verbatim in every brief. Classification (fact vs decision vs
outcome) needs cross-feature context the executor doesn't have; triage belongs to the
planner. The executor writes a divergence report (kbuild's template) and sets the
spec's Decomposition row to diverged. -->
