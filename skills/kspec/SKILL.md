---
name: kspec
description: Turn a feature idea into a signed intent spec with work briefs and planner-authored acceptance tests. Use when the user wants to plan, spec, or design a feature; triage a diverged milestone; re-plan after a divergence or change of direction; or close a finished feature with an intent-conformance review.
argument-hint: "<intent dump> | triage <feature> | replan <feature> [M<N>…] | close <feature>"
metadata:
  version: "1.0.0"
---

# kspec — planner sessions

The human owns what to build and why. Executors own how. This session owns the
translation: a spec an executor can act on without the conversation that produced it,
and acceptance tests that define done before any implementation exists.

```
/kspec <intent dump>             # plan a new feature (default mode)
/kspec triage <feature>          # triage a divergence report
/kspec replan <feature> [M<N>…]  # re-planning pass for affected milestones
/kspec close <feature>           # feature-close review — fresh session only
```

Artifacts — spec path from `.devops-ai/project.md` (Paths → Specs; default `docs/specs/`):

| Artifact | Location |
|----------|----------|
| Intent spec | `docs/specs/<feature>/SPEC.md` — template `intent-spec.md`, in this skill's directory |
| Work briefs | `docs/specs/<feature>/briefs/M<N>-<slug>.md` — template `work-brief.md`, same place |
| Acceptance tests | `tests/acceptance/<feature>/` |
| Glossary | `docs/specs/GLOSSARY.md` — concepts the human has been taught |
| Archive | `docs/specs/_archive/<feature>/` — specs of closed features |

**The writing rule, all modes:** every sentence you put in a spec or brief is a **fact**
about the world, a **decision** already made, a **testable end state**, or a
**directive** the human explicitly owns ("directive — human: …"). Never a process
instruction to the executor — the path from brief to delivered milestone is the
executor's to find. When you catch yourself writing "start by…" or "first refactor…",
you've found either a decision to make explicit or a sentence to delete.

## plan

**In:** the human's intent dump — his thinking in whatever state it's in; extracting
what's missing is your job, not his.
**Out, all committed before the session ends:** SPEC.md, one brief per milestone,
runnable acceptance tests, his sign-off.

No fixed script — loop freely between these obligations until sign-off is earned:

- **Remove ambiguity by asking, never by assuming.** Interview until no material
  ambiguity remains. Anything you inferred rather than heard goes in Assumptions, and
  becomes a decision only by his explicit word at sign-off.
- **Ground him before he decides.** When a question or decision depends on a region of
  code, walk him through that region first — what's there, how it's shaped, what
  changed since he last looked. Just-in-time, serving the decision at hand; never a
  ritual tour at session start. Add taught concepts to the glossary.
- **Investigate before drafting.** Read the code the feature touches and the archived
  specs of its neighbors. If the code contradicts the intent's premises, challenge the
  scoping — you have standing. What you find that an executor won't cheaply rediscover
  goes in Discovered context.
- **Escalate options-first.** His decisions: high blast radius or hard to reverse —
  data models, security-relevant behavior, external contracts, anything constraining
  future features. Present the tension, the options, and their consequences in terms
  he's been taught; give your recommendation after he states a leaning, or immediately
  if he asks. If he can't form a leaning, teach before deciding. Contained, reversible
  choices are yours — make them and record them as decisions.
- **Decompose into vertical slices.** Each milestone is user-visible, demonstrable
  end-to-end (`vertical-slicing` rule). A milestone that only makes sense as a
  prerequisite for another is a disguised step — merge them. Independent milestones may
  run in parallel. There are no tasks.
- **Author the acceptance tests now.** For each milestone, before any implementation:
  end-to-end tests exercising the brief's pinned **Surface** (`test-quality` rule).
  Every job has ≥1 blocking test; every blocking test covers a job. If you can't write
  the test, the Surface isn't pinned — that's a planning gap to close, not a test to
  defer. Run them: they must fail because the surface doesn't exist yet, not because
  the test is broken. Durable structural invariants additionally become architecture
  tests (`structural-gates` rule), not prose.

**Sign-off is his word, not his silence.** Walk him through the draft and every
Assumption; each is confirmed (promote it into the spec proper) or corrected. He says
it's signed; you fill `Signed off`, commit everything, and only then is the feature
executable.

**Done when:**
- SPEC.md is one page plus briefs, every sentence passing the writing rule
- every brief pins its Surface and carries the escape valve (the template's closing block — never trim it)
- jobs ↔ blocking tests cover each other both ways
- acceptance tests are committed and fail for the right reason
- Assumptions are empty (promoted or corrected) and `Signed off` carries his word

## triage

**In:** a spec with a `diverged` Decomposition row — an executor hit the escape valve
and reported without classifying. Classification is yours; so is skepticism.

1. **Verify the report against the code.** Executors can be wrong too — reproduce the
   contradiction before acting on it.
2. **Classify and act:**
   - **False fact** in the spec → correct the spec.
   - **Untenable decision** → switch to `replan` for the affected milestones.
   - **Wrong outcome** — a job itself doesn't hold up → the human, always,
     options-first. No model renegotiates what a feature is for.
3. **Record:** append an Amendment entry (unchecked box — pending his acknowledgment),
   reset the milestone's status, commit. The executor won't start the next milestone
   while a box is unchecked; your job is to make the pending flag impossible to miss.

## replan

The only context besides `plan` where acceptance tests may change.

**In:** a feature and the milestones affected by a triage outcome or the human's change
of direction. Rerun investigation → drafting → sign-off, scoped: redraft those briefs
and their acceptance tests, leave every other milestone's brief and tests untouched.
Append an Amendment entry, get sign-off on the delta, commit.

## close

**Fresh session only.** If this conversation planned or built any part of the feature,
stop and tell the human to run `/kspec close` in a new session — drift is invisible to
the hands that made it.

**In:** SPEC.md plus the whole feature's diff — collect the milestone PRs by their
`Spec: … · Milestone: M<N>` body lines.
**The one question:** taken together, do the changes satisfy the spec's *Intent*
paragraph — not merely its listed criteria? Everything mechanically checkable was
already checked per-milestone; this review is deliberately small.
**Out:** a short report to the human; corrective milestones appended to the
Decomposition if drift is found. Then his call on promoting the feature's acceptance
tests into the standing `tests/e2e/` suite; move the spec directory to
`docs/specs/_archive/`, mark the spec `closed`, commit.

## Authority

This file is operationally sufficient — no required reading. The contract it
implements, `docs/designs/v2-contract/CONTRACT.md` in the devops-ai repo, is where the
rationale lives: consult it when judgment runs past these instructions, and if the two
ever disagree, the contract wins and this file has a bug worth reporting.
