---
name: kbuild
description: Execute tasks (TDD) and orchestrate milestones from implementation plans. Attended fallback — kloop is the autonomous path.
metadata:
  version: "0.3.0"
  status: frozen
---

# Build Command

> **Frozen (2026-06).** kbuild is the attended fallback; autonomous execution runs
> through `kloop` (one task per fresh context, verifier-enforced). No further
> investment in this file — what a build run teaches goes into the gates
> (`templates/test_invariants.py`), the Stop hook, or kloop, never into prose here.
> If kloop proves out on real milestones, kbuild gets deleted.

Execute implementation-plan tasks with TDD, or orchestrate a whole milestone by sequencing
tasks with verification between them.

## Modes

- **Single task:** `/kbuild impl: <milestone-file> task: <task-id>`
- **Full milestone:** `/kbuild impl: <milestone-file>` — run tasks in order. A task isn't done
  until it *converges* (see "A task converges" below): all gates green, structural review clean,
  the change committed, and the handoff reflects it.
  Resume a partial milestone by reading the handoff for the first incomplete task.

## Context

Milestone frontmatter references the design and architecture docs:

```markdown
---
design: docs/designs/feature/DESIGN.md
architecture: docs/designs/feature/ARCHITECTURE.md
---
```

Read them before building. If they're missing and none are passed as parameters, ask.

## Build the context you lack, then build the feature

Before writing code, get yourself to the point where the task holds no surprises: the design
intent, the shape of the code you're touching, the patterns this codebase already uses, and the
gotchas the handoff recorded. Scale this to what you don't already know — a one-line fix in a
module you just wrote needs none of it; a new subsystem needs all of it. The goal is *no
surprises mid-implementation*, not a fixed ritual.

If something contradicts the task's assumptions (files absent, patterns missing, code already
changed), that's signal — verify with a second angle before proceeding, and report it rather than
coding around a guess.

Part of that context is **prior art**: before building a capability, name the existing mechanism
you're extending — or state in the handoff that you searched and nothing does this job. The
default is reuse; a new mechanism needs a reason. Agents writing rather than reading is how a
seven-milestone codebase ends up doing one thing three ways, and no functional gate catches it —
the claim is checkable, and the milestone structure pass checks it.

Implementation plans carry **code samples that show structure and wiring, not finished behavior.**
Read them for the pattern, then implement the real thing against the real code. Transcribing a
sample verbatim is not implementing.

## Task types

- **CODING** — TDD (see the `tdd` rule): failing test first, minimal pass, refactor.
- **RESEARCH** — investigation/analysis/docs; no TDD.
- **MIXED** — research, then TDD for the implementation portion.
- **VALIDATION** — real E2E against the running sandbox. The contract:
  - Work against a real sandbox. Discover it with `kinfra status`; start it (`kinfra sandbox
    start`) or rebuild after code changes (`kinfra sandbox rebuild`) as needed. A "sandbox
    unavailable" assumption is almost always a skipped discovery step, not a real blocker.
  - Tests are catalog recipes run by the ke2e agents, not hand-written pytest: invoke
    **ke2e-test-scout** (finds or designs recipes), then **ke2e-test-runner** (executes, reports
    PASS/FAIL with evidence).
  - **E2E means real external calls.** A test using mocks or seeded data is an integration test —
    correct by name, just not E2E. The distinction matters because the completion report is an
    interface contract reviewers trust (see below).

## Implementation (CODING)

TDD per the `tdd` rule; quality gates per the `quality-gates` rule; structural invariants per
the `structural-gates` rule. If infrastructure is configured, also run an integration smoke
test — start the system, exercise the changed flow, read the logs — because passing unit tests
on an unstarted system proves less than it looks.

## A task converges; it doesn't just finish

Run the task as a loop, as many times as it takes:

1. **Gates** — tests, quality checks, structural invariants. Red → fix the code, rerun. A gate
   is never fixed by editing the gate.
2. **Structural review** — when gates are green, have a fresh-context subagent review the task's
   diff with two lenses: *conformance* (does this violate boundaries the architecture doc
   states?) and *consolidation* (does it duplicate a mechanism that exists, or would a reviewer
   ask for it to be smaller, flatter, or merged with something nearby?). Fresh context is the
   point — the hands that wrote the code can't grade its shape.
3. **Converge** — confirmed findings get fixed via TDD, then back to step 1. Triage critically
   (a reviewer can be wrong; trace before you act). A clean review closes the loop.

Three cycles without convergence means the disagreement is real — stop and surface it to Karl
rather than grinding. And if what you keep fighting is the architecture itself, that's an ACP
(next section), not a fourth cycle.

## When the architecture is the problem: propose, don't route around

Sometimes the friction is real: a contract you keep needing exceptions to, a scenario the design
genuinely doesn't fit. You are empowered — expected — to propose an architecture evolution. You
are not empowered to make one silently.

Write an **ACP** (`templates/acp.md` → `docs/designs/<feature>/acp/ACP-NNN.md`): the friction
evidence, the design-level diagnosis, the proposed change, the **enforcement delta** (which
contract changes — no delta means it's a refactor or a workaround, not an evolution), and the
migration cost priced into a named milestone. Then keep implementing the task under the
*current* architecture — pause only if genuinely blocked. The evolution, if approved, lands as
its own task with its own diff; never bundled into the feature's.

A fresh-context **critique agent** reviews the ACP adversarially before it reaches Karl: is this
the design's problem or this task's inconvenience? does it create a second way of doing
something that already has a way? does the enforcement delta actually close the loop? is the
migration priced or hand-waved? Refuted → log it in the handoff and proceed under the current
design. Endorsed → it goes to Karl as a one-screen decision.

## Handoff (every task)

Update `HANDOFF_<feature>.md` per the `handoffs` rule (create it in the plan directory if absent).
It's the highest-value cross-session artifact — what you learned that the code alone won't tell
the next session.

## The bar for closing a milestone: the interaction surface is examined

Per-task TDD verifies each feature in isolation, so the defects that survive it are the ones no
single task owns: two individually-correct features that corrupt state *together* — a "move the
date freely" feature and a "snapshot absorbs past events" feature combining to silently resurrect
a paid bill. Line-by-line review never sees these; they surface only when something reasons across
the whole diff and the interaction surface.

So "all tasks done and green" is not the bar for closing a milestone. The bar is: **you have
adversarially examined the interaction surface and can say, concretely, which cross-feature
scenarios you traced and why none corrupt state** — where the scenarios that matter are every
prior feature that touches the *same state* (table, dedup key, balance walk, status field) as
something new. A milestone where those pairings went unexamined together is not finished, however
green the unit tests. Hold the same bar for the negative space: what each new write rejects, not
just what it accepts.

How you clear that bar is yours — a fresh-context subagent reviewing `git diff <main>...HEAD` is
well-suited to it (no attachment to the code, room to trace), but the examined-surface *outcome*
is what's required, not any particular mechanism. Two things make the outcome trustworthy rather
than performative: triage findings critically (a reviewer can be wrong; a claimed silent
corruption in load-bearing code earns your own trace before you act), and fix what's real via TDD
(a failing test that reproduces it first). Record in the handoff what you examined and concluded.
Clearing this bar *before* the PR is the point — it catches the bug class line-level review won't,
and pre-empts the review rounds that would otherwise find the cheaper half of it.

## The structure pass at milestone close

Before VALIDATION, review the milestone's whole diff for what no single task could see: a job
now done in two-plus places that should be one, a file that grew past its budget through small
legitimate additions, a pattern that drifted from its siblings, a prior-art claim that didn't
hold. A fresh-context subagent over `git diff <main>...HEAD` with the consolidation lens is
well-suited. The top findings become a fix-now task inside this milestone, gated like any
other — consolidation at the milestone that created the duplicate is one extraction task;
discovered five milestones later, it's archaeology.

## Reconcile the architecture at milestone close

When a milestone's tasks are done, the design/architecture docs are the spec the *next* `/kplan`
reads — so they must match what you actually built, or the next milestone gets planned off a
stale doc. This is the loop's most common slow failure, which is why it's a step, not a hope.

Diff what you built against the `design:`/`architecture:` docs and find the **design-level**
deltas — changes to the data model, state model, a contract/wire shape, an enum, an invariant, an
API surface (not implementation detail). For each delta, ask: did it come through an approved
ACP?

- **Intentional** (ACP-backed) → amend the doc to match, surgically.
- **Unintentional** (no ACP) → that's drift; editing the doc to match would legalize it.
  Collect these into a **bless-or-fix list** for Karl: for each, he either blesses it (the doc
  is amended, and the enforcement contract updated if one should have caught it) or it becomes
  a fix task before the milestone closes.

Resolve any internal contradiction in the docs and mark which representation is normative so it
can't re-drift. If a decision is genuinely *open* (not merely undocumented), surface it rather
than inventing a spec.

Report what you reconciled (or "no architectural deltas"). A milestone that changed a contract but
left the architecture untouched isn't finished — and neither is one whose drift list is silently
self-approved.

## Milestone completion report

This is an interface contract — PR creation reads it. Produce it when the milestone's tasks are
done.

It must tell the truth about testing, because a reviewer can't re-run your work — they trust this
table. So before listing a test as E2E, confirm it made real external calls and that you watched
it pass. Mocked or seeded tests go under Integration, not E2E; listing them as E2E makes the
report untruthful, which is worse than a thin E2E section.

```markdown
## Milestone Complete: [Name]

**Tasks completed:** X.1–X.N · **Quality gates:** All passed

### E2E Tests Performed  (real external calls only)
| Test | Real calls to... | Result |
|------|------------------|--------|

### Integration Tests
| Test | Result |
|------|--------|

### Challenges & Solutions
| Task | Challenge | Solution |
|------|-----------|----------|

### Interaction surface examined  (the close-out bar)
<!-- Name the cross-feature/same-state scenarios you traced and why each is safe — this is the
     evidence the bar was met, not that a step ran. Then the findings it produced: -->
| Finding | Severity | KEEP/SKIP | Action |
|---------|----------|-----------|--------|

### Structure pass  (consolidation findings and what was fixed)
| Finding | Fixed in task / deferred (why) |
|---------|--------------------------------|

### ACPs raised this milestone
| ACP | Verdict (critique) | Decision (Karl) |
|-----|--------------------|-----------------|

### Architecture Reconciliation  (design-level deltas)
| Delta (reality vs. doc) | Via ACP? | Blessed / Fixed | Doc amended |
|-------------------------|----------|-----------------|-------------|

### Failed Tests (not due to this work)
| Test | Failure | Status |
|------|---------|--------|

### E2E Catalog Tests Executed  (recipes run by ke2e-test-runner)
| Recipe | Result | Category if failed |
|--------|--------|--------------------|

### E2E Gate  (required — milestone isn't complete if these aren't true)
- ke2e-test-scout invoked · ke2e-test-runner invoked · recipes PASSED or failures categorized ·
  no unresolved ENVIRONMENT failures
```

Omit empty sections, except the E2E Gate. If no recipes exist for these changes, have
ke2e-test-scout confirm it and record the gap — don't just write "no E2E tests."

## When blocked or contradicted

Blocked → don't mark the task done; document the blocker and ask. If a task's instructions
contradict this skill, follow the task — it has context this skill doesn't.
</content>
