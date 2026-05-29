# PROPOSAL: kbuild de-restricted (candidate rewrite)

**Status:** Proposal for review — NOT applied to the live skill. If Karl approves, this replaces
`skills/kbuild/SKILL.md`.
**Principle applied:** Latitude on method, rigor on verification (`INTENT.md` §1).
**Method:** Every prescriptive step / `DO NOT` was triaged as *contract* (keep, state the why),
*method-restriction* (relax to goal-framing), or *scar tissue* (convert prohibition → contract +
the failure it prevents). Nothing was deleted that encodes a real engineering lesson; lessons were
re-expressed as rationale the model can generalize from.

A change-map (what moved and why) follows the rewrite.

---

## ▼ CANDIDATE SKILL.md

```markdown
---
name: kbuild
description: Execute tasks (TDD) and orchestrate milestones from implementation plans.
metadata:
  version: "0.2.0"
---

# Build Command

Execute implementation-plan tasks with TDD, or orchestrate a whole milestone by sequencing
tasks with verification between them.

## Modes

- **Single task:** `/kbuild impl: <milestone-file> task: <task-id>`
- **Full milestone:** `/kbuild impl: <milestone-file>` — run tasks in order. A task isn't done
  until its tests pass, quality gates pass, the change is committed, and the handoff reflects it.
  Resume a partial milestone by reading the handoff for the first incomplete task.

## Context

Milestone frontmatter references the design and architecture docs:

\```markdown
---
design: docs/designs/feature/DESIGN.md
architecture: docs/designs/feature/ARCHITECTURE.md
---
\```

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

TDD per the `tdd` rule; quality gates per the `quality-gates` rule. If infrastructure is
configured, also run an integration smoke test — start the system, exercise the changed flow,
read the logs — because passing unit tests on an unstarted system proves less than it looks.

## Handoff (every task)

Update `HANDOFF_<feature>.md` per the `handoffs` rule (create it in the plan directory if absent).
It's the highest-value cross-session artifact — what you learned that the code alone won't tell
the next session.

## Reconcile the architecture at milestone close

When a milestone's tasks are done, the design/architecture docs are the spec the *next* `/kplan`
reads — so they must match what you actually built, or the next milestone gets planned off a
stale doc. This is the loop's most common slow failure, which is why it's a step, not a hope.

Diff what you built against the `design:`/`architecture:` docs and find the **design-level**
deltas — changes to the data model, state model, a contract/wire shape, an enum, an invariant, an
API surface (not implementation detail). For each: the tested-and-validated code is the source of
truth, so amend the doc to match, surgically. Resolve any internal contradiction in the docs and
mark which representation is normative so it can't re-drift. If a decision is genuinely *open*
(not merely undocumented), surface it rather than inventing a spec.

Report what you reconciled (or "no architectural deltas"). A milestone that changed a contract but
left the architecture untouched isn't finished.

## Milestone completion report

This is an interface contract — PR creation reads it. Produce it when the milestone's tasks are
done.

It must tell the truth about testing, because a reviewer can't re-run your work — they trust this
table. So before listing a test as E2E, confirm it made real external calls and that you watched
it pass. Mocked or seeded tests go under Integration, not E2E; listing them as E2E makes the
report untruthful, which is worse than a thin E2E section.

\```markdown
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

### Architecture Reconciliation  (design-level deltas folded back into the docs)
| Delta (reality vs. doc) | Doc amended |
|-------------------------|-------------|

### Failed Tests (not due to this work)
| Test | Failure | Status |
|------|---------|--------|

### E2E Catalog Tests Executed  (recipes run by ke2e-test-runner)
| Recipe | Result | Category if failed |
|--------|--------|--------------------|

### E2E Gate  (required — milestone isn't complete if these aren't true)
- ke2e-test-scout invoked · ke2e-test-runner invoked · recipes PASSED or failures categorized ·
  no unresolved ENVIRONMENT failures
\```

Omit empty sections, except the E2E Gate. If no recipes exist for these changes, have
ke2e-test-scout confirm it and record the gap — don't just write "no E2E tests."

## When blocked or contradicted

Blocked → don't mark the task done; document the blocker and ask. If a task's instructions
contradict this skill, follow the task — it has context this skill doesn't.
```

---

## Change-map: what moved, and why it's safe

| Section | Was | Now | Triage |
|---|---|---|---|
| Research First | 4 numbered mandatory steps + "Output a brief summary (2–4 sentences)" | "Build the context you lack" — goal-framed, explicitly scaled to what the model already knows | **Method-restriction → relaxed.** The goal (no surprises mid-build) is preserved; the fixed ritual isn't. This is the strain-log's worked example, applied. |
| VALIDATION "Do NOT skip" / "stop:" | `Do NOT skip this step`, `If you catch yourself... stop` | "A 'sandbox unavailable' assumption is almost always a skipped discovery step"; "a mocked test is an integration test, correct by name" | **Scar tissue → contract + why.** The lesson (don't fake E2E, don't skip discovery) survives as rationale the model generalizes; the prohibition framing goes. |
| Architecture Reconciliation | "**It is not optional.**" + 4 numbered steps | "which is why it's a step, not a hope" + prose stating the same deltas/normative-doc logic | **Contract kept, method relaxed.** The outcome (docs match reality) is non-negotiable and stays; the step-by-step procedure becomes intent. |
| Completion report | "MUST NOT appear", "untruthful report", verbatim verification questions | "it must tell the truth about testing, because a reviewer can't re-run your work" | **Verification rigor kept, stated as why.** This is the clearest case of "rigor on verification": the honesty contract is *strengthened* by explaining the reviewer-trust reason, not weakened. |
| Report template | ~50 lines, one row-comment per cell | compact, same columns, comments collapsed | **Method.** Same interface contract, less ceremony around it. |
| Overall | 188 lines | 144 lines (~23%) | Side effect, not the goal. (An earlier draft of this doc claimed ~95; that was an inaccurate estimate — corrected against the applied file.) |

## What I deliberately did NOT touch

- **TDD / quality-gates / handoffs / e2e contracts** — delegated to rules already; untouched.
- **The E2E honesty requirement** — *strengthened* (now reasoned), never relaxed.
- **The reconciliation outcome** — still mandatory; only its procedure is de-prescribed.
- **The completion report as an interface contract** — preserved; reviewers depend on it.

## Honest uncertainty

I can't know from the text alone whether the *why-framing* is sufficient where the old `DO NOT`
was load-bearing — i.e. whether Opus 4.8 actually honors "E2E means real calls" stated as a
contract as reliably as it honored "DO NOT write pytest for E2E." **That is precisely the
CashFlow observation's job:** run a VALIDATION task under this rewrite and watch whether the E2E
classification stays honest without the prohibition. If it drifts, the prohibition was earning its
keep and goes back — as a contract with teeth, not as proof the principle failed.
</content>
