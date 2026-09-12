---
name: kspec
description: Turn a feature idea into a signed intent spec with work briefs and planner-authored acceptance tests. Use when the user wants to plan, spec, or design a feature; triage a diverged milestone; re-plan after a divergence or change of direction; or close a finished feature with an intent-conformance review.
argument-hint: "<intent dump> | triage <feature> | replan <feature> [M<N>…] | close <feature>"
metadata:
  version: "1.1.0"
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

**Model check, first thing, every mode:** say which model this session runs on. A
planner runs on the strongest frontier model; if this session is on the executor tier
(carried over from a child session, or resumed on a default after a restart), stop and
say so. The pilot ran a replan on the wrong tier twice before anyone read the status bar.

Artifacts — spec path from `.devops-ai/project.md` (Paths → Specs; default `docs/specs/`):

| Artifact | Location |
|----------|----------|
| Intent spec | `docs/specs/<feature>/SPEC.md` — template `intent-spec.md`, in this skill's directory |
| Work briefs | `docs/specs/<feature>/briefs/M<N>-<slug>.md` — template `work-brief.md`, same place |
| Acceptance tests | `tests/acceptance/<feature>/` |
| Divergence reports | `docs/specs/<feature>/divergences/` — written by executors, resolved here |
| Close report | `docs/specs/<feature>/CLOSE.md` — template `feature-close-report.md` |
| Glossary | `docs/specs/GLOSSARY.md` — template `glossary.md`; concepts the human has been taught |
| Archive | `docs/specs/_archive/<feature>/` — specs of closed features |

**Branch:** briefs and acceptance tests are planner-owned — the CI guard rejects changes
to them from any branch except `spec/*` and `replan/*`. Work on `spec/<feature>`
(`kinfra spec <feature>` creates the worktree) for `plan`, and `replan/<feature>` for
`triage`/`replan` outcomes that touch briefs or tests. Never wire infrastructure (a
guard, a workflow, a CI step) into a project PR without a labeled human directive: that
is a change to what he signed, not a planning artifact.

**The writing rule, all modes:** every sentence you put in a spec or brief is a **fact**
about the world, a **decision** already made, a **testable end state**, or a
**directive** the human explicitly owns ("directive — human: …"). Never a process
instruction to the executor — the path from brief to delivered milestone is the
executor's to find. When you catch yourself writing "start by…" or "first refactor…",
you've found either a decision to make explicit or a sentence to delete. A decision is
recorded with the alternative it rejected — that is what makes it re-litigable later
without the conversation.

## plan

**In:** the human's intent dump — his thinking in whatever state it's in; extracting
what's missing is your job, not his.
**Out, all committed before the session ends:** SPEC.md, one brief per milestone,
runnable acceptance tests, his sign-off, and a hand-off to `kobserve` for launch.

No fixed script — loop freely between these obligations until sign-off is earned:

- **Remove ambiguity by asking, never by assuming.** Interview until no material
  ambiguity remains. Anything you inferred rather than heard goes in Assumptions, and
  becomes a decision only by his explicit word at sign-off. Keep two questions apart:
  *what should the system allow?* (framework semantics, a decision for the spec) and
  *what do you want for yours?* (instance configuration, an answer for his deployment).
  Asked as one, the second arrives dressed as the first.
- **Ground him before he decides.** When a question or decision depends on a region of
  code, walk him through that region first — what's there, how it's shaped, what
  changed since he last looked. Just-in-time, serving the decision at hand; never a
  ritual tour at session start. Add taught concepts to the glossary.
- **Investigate before drafting.** Read the code the feature touches and the archived
  specs of its neighbors. If the code contradicts the intent's premises, challenge the
  scoping — you have standing. What you find that an executor won't cheaply rediscover
  goes in Discovered context.
- **Escalate options-first.** His decisions: high blast radius or hard to reverse —
  data models, security-relevant behavior, external contracts, **product semantics**
  (what a user-visible state means), anything constraining future features. Present the
  tension, the options, and their consequences in terms he's been taught; give your
  recommendation after he states a leaning, or immediately if he asks. If he can't form
  a leaning, teach before deciding. Contained, reversible choices are yours — make them
  and record them as decisions, each with its rejected alternative.
- **Decompose into vertical slices.** Each milestone is user-visible, demonstrable
  end-to-end (`vertical-slicing` rule). A milestone that only makes sense as a
  prerequisite for another is a disguised step — merge them. Independent milestones may
  run in parallel. There are no tasks.
- **Pin a self-contained Surface.** Every field a brief pins is defined in that brief.
  Anything that enumerates, renders or lists the thing the brief adds is Surface too
  (the pilot added a scope and forgot the UI that lists scopes). A dev-only seam pinned
  for the tests carries its semantics like any route. Every pinned side effect states
  what happens when its channel is down. A UX shape that *is* the product intent is
  labeled a human directive with the reason. The brief's **Working environment** states
  the repository's standing PR gates and their scope, every toolchain's setup step, and
  the runtime facts the tests depend on.
- **Author the acceptance tests before the sign-off walkthrough.** For each milestone:
  end-to-end tests exercising the brief's pinned **Surface**, worked through the
  acceptance-test checklist in the `test-quality` rule — if a test asserts it, the
  Surface states it; the **opposite reading** of every decision; clock and timezone;
  run-to-the-end; rendered output for UI; failure paths. Every job has ≥1 blocking
  test; every blocking test covers a job. If you can't write the test, the Surface
  isn't pinned — a planning gap to close, not a test to defer. Writing the tests is the
  sharpest ambiguity detector you have; what they surface belongs in front of him.
  Durable structural invariants additionally become architecture tests
  (`structural-gates` rule), not prose.
- **Measure, don't assert.** Run the tests against a *running sandbox in the executor's
  runtime* — sandbox ports, environment, clock — before sign-off. They must fail because
  the surface doesn't exist yet, not because the test is broken. Every "passes/fails on
  main" claim in a Blocking table is measured; the table's **Measured on main** column
  carries the command and its output. The pilot's one divergence was an inferred claim.
  An integration-level blocking test is legal only when the live stack cannot exercise
  the job, labeled with the reason and its baseline in that same table.

**Sign-off is his word, not his silence — a per-item yes.** Walk him through the draft:
every Assumption, and for each brief a short **what the tests pin** list (the values and
shapes the acceptance tests assert, in his terms). Each item is confirmed (promote it
into the spec proper) or corrected. A partial reply — one item answered, another
"I don't understand" — reopens the gate: teach, then ask again. He says it's signed; you
fill `Signed off`, commit everything, and the spec PR goes through the review loop like
any PR (the pilot's spec PR review found three real findings, one a fossil in a test
fixture the sign-off never saw). Only then is the feature executable — hand off to
`kobserve` to launch.

**Done when:**
- SPEC.md is one page plus briefs, every sentence passing the writing rule
- every brief pins its Surface (self-contained, complete, failure paths, working
  environment), states its exact `blocking:` command, carries the Measured-on-main
  column filled, and carries the escape valve (the template's closing block — never
  trim it)
- jobs ↔ blocking tests cover each other both ways, and every value a test asserts is
  stated in its brief
- acceptance tests are committed, checked against the executor's runtime, and fail for
  the right reason
- Assumptions are empty (promoted or corrected), `Signed off` carries his per-item word,
  and the spec PR is babysat to merge-ready

## triage

**In:** a spec with a `diverged` Decomposition row and the divergence report it points
to — an executor hit the escape valve and reported without classifying. Classification
is yours; so is skepticism.

1. **Verify the report against the code.** Executors can be wrong too — reproduce the
   contradiction on a running stack before acting on it.
2. **Classify and act:**
   - **False fact** in the spec → correct the spec.
   - **Untenable decision** → switch to `replan` for the affected milestones.
   - **Wrong outcome** — a job itself doesn't hold up → the human, always,
     options-first. No model renegotiates what a feature is for.
3. **Record:** fill the report's *Planner resolution* section, append an Amendment entry
   of the right kind — a false fact is a **pre-checked fact-correction** (`- [x]`, blocks
   nothing); an untenable decision or a changed outcome is an **unchecked** entry pending
   his acknowledgment — reset the milestone's status, commit. The executor won't start
   the next milestone while a box is unchecked; your job is to make the pending flag
   impossible to miss.

**Fact corrections that arrive in a PR** (an executor's *Facts I corrected* section, per
the `outcome-contracts` rule) are not divergences: verify each against the code, amend
the spec with a pre-checked fact-correction entry, done. If one of them changed what was
built, it was misfiled — treat it as a divergence from here.

## replan

The only context besides `plan` where acceptance tests may change.

**In:** a feature and the milestones affected by a triage outcome, an executor's *For the
human* item the human chose to fix now, or his change of direction. Rerun investigation
→ drafting → sign-off, scoped: redraft those briefs and their acceptance tests (same
checklist, same measurement), leave every other milestone's brief and tests untouched.
Append an Amendment entry with the rejected alternative, get his per-item sign-off on
the delta, commit.

## close

**Fresh session only.** If this conversation planned or built any part of the feature,
stop and tell the human to run `/kspec close` in a new session — drift is invisible to
the hands that made it.

**In:** SPEC.md plus the whole feature's diff — collect the milestone PRs by their
`Spec: … · Milestone: M<N>` body lines, and every *For the human* item he deferred.
**The one question:** taken together, do the changes satisfy the spec's *Intent*
paragraph — not merely its listed criteria? Everything mechanically checkable was
already checked per-milestone; this review is deliberately small. Its adversarial half
drives a lifecycle to its end from an angle the blocking tests didn't take.
**Out:** a short report to the human (`feature-close-report.md` → `CLOSE.md`);
corrective milestones appended to the Decomposition if drift is found — each with a
brief and planner-authored blocking tests, for his sign-off; and an *Outside the
outcomes* section for what you saw that is not this feature's drift (roadmap notes).

**Two-pass when drift is found:** the spec stays `closing`; the corrective milestones
run; a *second* fresh close session, from a different adversarial angle, confirms before
anything is archived.

**Archiving:** his call on each acceptance test — promote by kind (`tests/e2e/`,
`tests/integration/`, `tests/unit/`) or drop; `grep` the repository for the spec's path
before moving it (the pilot's sweep missed a reference in a SQL comment) so every
outside reference follows; move the spec directory to `docs/specs/_archive/`, mark the
spec `closed`, commit.

## Authority

This file is operationally sufficient — no required reading. The contract it
implements, `docs/designs/v2-contract/CONTRACT.md` in the devops-ai repo, is where the
rationale lives: consult it when judgment runs past these instructions, and if the two
ever disagree, the contract wins and this file has a bug worth reporting.
