<!--
INTENT SPEC — one per feature. Lives at docs/specs/<feature>/SPEC.md (path configurable
via .devops-ai/project.md → Paths → Specs). Work briefs live beside it in briefs/,
acceptance tests in tests/acceptance/<feature>/. At feature close the spec directory
moves to docs/specs/_archive/<feature>/.

THE LINT (a warning, not a law): every sentence in this spec should be a FACT about the
world, a DECISION already made, or a TESTABLE END STATE. A fourth kind is legal but must
be labeled — a DIRECTIVE, a path deliberately prescribed by the human for reasons outside
the codebase ("directive — human: use provider X, contract already signed"). Directives
are the human's alone; a model that wants to prescribe a path makes a decision, which is
challengeable. An unlabeled process instruction ("start by refactoring…") is the smell
this lint exists to catch.

One page plus briefs. If the intent won't fit a page, it's probably two features.
-->

# <Feature name>

**Status:** planning | in progress | closing | closed
**Signed off:** <!-- date + "Karl" once the human has corrected and signed the draft; empty until then -->

## Intent

<!-- One paragraph: what changes and why. This is the touchstone for the feature-close
review — the question that session answers is "taken together, do the changes satisfy
THIS paragraph?" -->

## Outcomes

<!-- Observable end states a stranger could verify. Not activities, not paths. -->

## Invariants

<!-- What must not change. Durable structural invariants should also land as
architecture tests (tests/architecture/) — enforced structure is run, not read. -->

## Non-goals

<!-- The explicit scope fence. -->

## Discovered context

<!-- What the planner's investigation found that an executor won't cheaply rediscover:
load-bearing quirks, adjacent features sharing state, past decisions from archived specs. -->

## Decomposition

<!-- One row per milestone. Each is a vertical slice — user-visible, demonstrable
end-to-end. A milestone that only makes sense as a prerequisite for another is a
disguised step: merge them. Status here is the cross-session progress state; there is
no other status artifact.

Status values: pending → in progress → diverged (awaiting triage) → PR → delivered.
On divergence, the executor adds an indented "Divergence:" block under the row —
what it found, verbatim per the escape valve, with no self-classification. -->

| Milestone | Brief | Jobs | Depends on | Status |
|-----------|-------|------|------------|--------|
| M1 — <name> | briefs/M1-<slug>.md | J1 | — | pending |

## Assumptions

<!-- Everything the planner inferred rather than heard. An assumption becomes a decision
only by the human's word — at sign-off, each line here is either confirmed (move it into
the section it belongs to) or corrected. -->

## Amendments

<!-- Append-only log of post-sign-off changes: divergence triage resolutions, re-planning
outcomes, corrected facts. Each entry is a flag; an unchecked box is PENDING the human's
acknowledgment. Starting any new milestone while a box is unchecked is blocked — the
executor stops and asks. This is what keeps the signature meaning something.

- [ ] YYYY-MM-DD (M2) fact-correction: <what was wrong, what is true now>
- [ ] YYYY-MM-DD (M3) decision-change: <what changed, via re-planning pass>
- [ ] YYYY-MM-DD (M1) outcome-change: <a job changed — decided by the human, never a model>
-->
