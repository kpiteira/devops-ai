---
name: kdesign
description: Design and validate features through collaborative exploration. Produces DESIGN.md, ARCHITECTURE.md, JTBDs, and a milestone structure.
metadata:
  version: "0.3.0"
---

# Design Command

Generate, validate, and refine design and architecture documents for a feature or system change —
a single conversation that replaces separate design, validation, and milestone-structure steps.

## What this produces

1. **DESIGN.md** — the what and why: problem, goals, non-goals, key decisions with trade-offs.
2. **Jobs To Be Done** — numbered job stories (J1, J2, …), each tagged to the milestone where the
   job first becomes doable end-to-end. Lives as a section in DESIGN.md.
3. **ARCHITECTURE.md** — the how: components, data flow, state, errors, interface signatures,
   integration points, and an **Enforcement** section mapping each structural decision to the
   check that holds it.
4. **Milestone structure** — vertical slices ready for planning, each listing the JTBDs it delivers.

```
/kdesign feature: <description> [context: <relevant-docs>]
```

## This is a conversation, not a generator

The value is in the back-and-forth, not the first draft. You know what's flaky, what failed
before, what "feels wrong"; Claude proposes and finds gaps, you decide. Gaps found now are
discoveries that save hours later — surface them, don't hide them behind a confident draft.

## What to explore

Depth scales to the feature. A two-hour change needs a paragraph and three job stories, not the
full treatment below. Match the ceremony to the stakes.

**Problem space.** What problem, for whom, what does success look like, what constrains us. Land a
2–3 sentence problem statement and get alignment before proposing solutions.

**Jobs to be done.** Enumerate the jobs the feature must satisfy, in job-story form: *When
⟨situation⟩, I want to ⟨motivation⟩, so I can ⟨outcome⟩.* Give each a stable ID (J1, J2, …). The
act of enumerating is the point — it surfaces capabilities a prose "scenarios" paragraph silently
drops. Include **client-as-user** stories where the system is API-first ("When I hand Claude Code
a screenshot, I want it to do everything the UI can via the API"). Each job gets tagged to exactly
one milestone later; that mapping is a coverage contract kplan enforces from both sides, so it's
worth getting real here rather than illustrative.

**Solution options.** Explore 2–3 approaches with trade-offs when the choice is live; a simple
feature with an obvious approach doesn't need invented alternatives. For each: how it works, what
it makes easy, what it makes hard, the risks. Recommend, with reasoning.

**Architecture.** Components and responsibilities; data flow; where state lives and its lifecycle;
what can go wrong and what happens; what existing code changes.

## Validation — trace scenarios to find gaps

Trace concrete scenarios through the architecture step by step (which component, what input, what
processing, what state change, what could go wrong). Cover happy paths and key variations, error
and recovery paths, edge cases (cancellation, concurrency, ambiguous transitions), and integration
boundaries. Tracing a scenario you just added is where surprises surface — do it live.

Gaps to hunt for:

- **State-machine** — transitions not covered, ambiguous intermediate states.
- **Error-handling** — failures with no defined behavior.
- **Data-shape** — undefined or ambiguous structures.
- **Integration** — unclear component boundaries or ownership.
- **Concurrency** — races, ordering.
- **Side-effect / command-query** — does a read mutate state? does an operation have a side-effect
  its name doesn't imply? where is each state change triggered, and is that the same surface as
  the read? (This is CQS hygiene — it catches the "a read is a read" class of bug, e.g. a `GET`
  that advances a frontier, before it's baked into the architecture.)

A gap is a decision to make, not a problem to report: present options, trade-offs, a
recommendation; record the decision.

## Implementation-readiness check (before you finish)

Behavioral gap-hunting misses a class of decision that isn't behavioral at all — how an entity is
*shaped* in storage and on the wire. These are cheap to decide on a whiteboard and expensive to
change once a schema and engine exist, so settle them before declaring the design done. For each,
a one-line decision or an explicit "deferred to milestone N (low risk)":

- **Units & money** — currency, decimal precision, integer-cents vs decimal.
- **Sign / direction** — signed values, or magnitude + direction-by-legs.
- **Identity** — id scheme; synthetic/derived ids; uniqueness keys.
- **Enums & nullability** — closed sets named; which fields are optional, and why.
- **Time** — date vs datetime; who owns the timezone; is "now" injectable (for tests)?
- **Side-effects / purity** — which operations are pure reads (ties to the gap category above)?

This is the hand-off contract to kplan: these are the choices kplan will otherwise invent in code.

## Enforcement — every structural decision names its check

Prose doesn't constrain the agents that will build this; gates do (the `structural-gates` rule).
So ARCHITECTURE.md closes with an **Enforcement** table: each decision that constrains code
structure, mapped to how it's held.

| Decision | Enforced by |
|----------|-------------|
| Domain stays transport-free | invariant: `domain/` never imports `api/` or `fastapi` |
| Result types live in one module | invariant: no `*Result` class outside `results.py` |
| Reads are pure | review-lens: named in kbuild's structural review |

Three kinds of entry: an **invariant** (machine-checked, lands in `tests/architecture/` — kplan
turns these into M1's harness task), a **review-lens** (a named lens for kbuild's structural
review, when no machine check can express it), or an explicit **unenforced** (a recorded
acceptance, never a default). A decision that can't name its check is usually too vague to
survive contact with implementation — sharpening it here is design work, not bureaucracy.

## Milestones

Propose a vertical milestone structure (the `vertical-slicing` rule has the principles): each slice
E2E-testable, building on the last, delivering user-visible value, and **listing the JTBD IDs it
delivers**. Milestone 1 is the smallest thing that proves the architecture works end-to-end —
testable, not necessarily useful. Every JTBD lands in exactly one milestone.

## Principles

- **Decisions over description** — capture *why*. "Uses a queue because operations take 30+s and we
  don't want to block the API" beats "uses a queue."
- **Acknowledge uncertainty** — name open questions rather than performing certainty. (You're better
  at flagging what you're unsure of than at being right by default — use that.)
- **Rosetta stone** — diagrams for humans (ASCII box-and-arrow), structured tables for LLM
  consumption; both carry the same information.
- **Interface signatures, not implementations** — method names, params, return types. If it could
  be pasted in as working code, it's too much detail. Enough to plan tasks, not to have built them.

## Conversation patterns that pay off

- *"What keeps you up at night?"* — after proposing scenarios, ask what feels risky even if hard to
  articulate. Reveals scenarios Claude wouldn't think of.
- *"What's the constraint?"* — when a gap has many options, the real constraint often collapses the
  decision.
- *"Does this remind you of anything?"* — past failures predict future ones.
- *"Let me trace that"* — trace an added scenario immediately.

## Output

Save under the configured design-documents path:

```
docs/designs/<feature-name>/
  DESIGN.md          (includes the Jobs To Be Done section)
  ARCHITECTURE.md
```

The milestone structure can close the design output or be a separate section — whatever fits.

**When validation reveals rework:** many critical gaps (>5) means the design needs another
iteration. Say so — cheaper now than after code.

**When design isn't needed:** skip formal docs for small obvious changes, learning spikes, or when
implementing is faster than documenting.
</content>
