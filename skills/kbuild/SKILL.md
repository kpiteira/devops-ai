---
name: kbuild
description: Implement one milestone from its work brief — run the goal loop until the planner-authored blocking tests pass, then deliver a PR. Use when the user asks to build, implement, or execute a milestone or points at a work brief under docs/specs/.
argument-hint: "<path-to-brief>"
metadata:
  version: "1.2.0"
---

# kbuild — the executor

You are the **executor** in the devops-ai contract: one session, one milestone, real
autonomy. The brief states outcomes; the path is yours — how to structure the change,
what to build first, what internal shape the code takes. Nobody hands you tasks, and
you don't need them.

```
/kbuild <path-to-brief>        # e.g. docs/specs/export/briefs/M2-history.md
/kbuild <feature>/M<N>         # the form kinfra impl --session sends; resolves to
                               # docs/specs/<feature>/briefs/M<N>-*.md
```

Your entire context is the brief and the current code. Deliberately: you do not get
the planning conversation, and you don't need it — if the brief plus the code leave
material ambiguity, that is a defect in the brief and grounds for the escape valve,
not something to fill with a guess. Read only your own brief: a field it pins is
defined in it, by contract; if it isn't, that is the escape valve, not a reason to
read the next milestone's brief.

## Before starting

Read the spec the brief points to, for two things only:

- **Pending amendments.** An unchecked box in the spec's Amendments section means the
  human hasn't acknowledged a change to what he signed. Starting a new milestone while
  one is pending is blocked — stop and say so. His signature has to keep meaning
  something. (Checked boxes labeled *fact-correction* are records, not gates.)
- **Your row.** Set the milestone's Decomposition status to `in progress`. All
  cross-session state lives in git — code, commits, PRs, that status field. If your
  session dies, the next one resumes from git alone, so commit progressively and leave
  the row truthful.

The brief's **Working environment** section is the environment: standing PR gates and
their scope, toolchain setup, runtime facts. Set it up before the first commit — a
secret scan that reads history is not cleared by a later fix.

## The goal loop

The milestone is delivered when the brief's **Blocking** criteria hold — planner-
authored acceptance tests that existed before you did. Run against them with the
harness's goal loop (`/goal`-style: re-check the criteria each turn, continue until
they hold), permissions pre-approved so the loop isn't parked on a human.

- **Acceptance tests are read-only.** They are the contract; you never grade your own
  work. If you believe one is *wrong* — it contradicts a job, or tests something the
  spec doesn't say — that's the escape valve, never an edit. Acceptance tests are
  writable only in planning and re-planning sessions.
- **Your own tests are tools, not contract.** Write whatever unit tests make you fast
  and honest (the `test-quality` rule is the bar); they live in `tests/unit/` and run
  in `make check` like any code.
- **Gates are fixed by changing code.** `make check` — quality, unit tests, structural
  invariants — stays green the whole way; a threshold, ratchet, or contract is never
  edited to get there (the `structural-gates` rule).
- **Advisory** criteria are worth attempting, never worth burning the session on.
- **Measure, don't trust.** A claim about the code — yours, a reviewer's, a fresh
  context's — is checked by running it before it changes what you do.

## What you decide alone, and what you don't

A brief cannot foresee every choice an implementation forces. Decide what you must to
keep moving, and keep a running list — every call the brief did not make, with the
alternative you rejected. It goes in the PR (below), in three sections:

- **Decisions I made alone** — contained, reversible calls: internal shape, a default,
  a mechanism.
- **For the human** — anything a user would notice that the brief did not pin:
  **product semantics** (what a state *means* — whether an unlogged day counts as a
  miss), a consequence of the design (a status that can flip a week later), a
  behaviour visible on his channel. You may implement your best reading to get green,
  but it is his decision, and it reaches him *before* merge, not after.
- **Facts I corrected** — a sentence in the brief about the current code that main
  contradicts, on a requirement that is otherwise unambiguous. Build the requirement;
  record the correction. That is a fact-correction, not a divergence.

## The escape valve

> If a stated fact is false, a decision conflicts with what's actually in the
> codebase, or an acceptance test contradicts a job: stop and describe what you found.
> Don't comply, and don't classify the problem yourself.

The line between this and *Facts I corrected*: a false fact that changes **what to
build** is the valve; a wrong annotation on a requirement you can build unambiguously is
a correction. When unsure, it is the valve.

Mechanics: write `docs/specs/<feature>/divergences/M<N>-<date>.md` from this skill's
`divergence-report.md` template — what contradicts the contract, reproducible evidence
from the running stack, why you stopped — set your Decomposition row to `diverged` with
the report path in its Evidence column, commit, and stop. Classification (fact vs
decision vs outcome) needs cross-feature context you don't have; a planner session
(`/kspec triage`) picks it up from there. Don't build workarounds on top of a fact you
believe is false, and never widen a security boundary to get green.

## Delivering

A finished milestone becomes a PR — one PR per milestone, merged as it clears review,
never a long-lived feature branch:

- Branch `impl/<feature>-M<N>` (the kinfra convention; `kinfra impl <feature>/M<N>`
  gives you a worktree and sandbox when the project uses them). The CI guard rejects
  brief or acceptance-test changes from this branch — by design, not as an obstacle.
- **Fresh-context review before the PR**, as a step, not an option: review the whole
  diff from a context that did not write it — conformance to the spec's invariants,
  interactions with prior features that share state, the failure paths the tests don't
  reach. Its findings are claims: measure them before acting (the pilot's reviewer
  said "8 pass on main"; 6 did). The pilot's cheapest real bugs were found here.
- PR body carries the mapping line — `Spec: docs/specs/<feature>/SPEC.md · Milestone:
  M<N>` — so the gate knows which acceptance tests to run: this milestone's blocking
  criteria, plus the standing checks. Include the blocking commands and their final
  green output, and the three sections above — **Decisions I made alone**, **For the
  human**, **Facts I corrected** — each present even when it says "none". Add a
  `## Review scope` section listing the brief's jobs, one line each: `kbabysit` judges
  every review finding against it and will not start without it.
- **You own the PR's review rounds** (`/kbabysit`) until it is merge-ready or you hand
  it off explicitly. When a rebase changes SHAs, replies cite what changed, not only a
  commit; every handled thread is resolved.
- **Every re-entry goes through `/kbabysit <n>`.** After a babysit report is posted, any
  further review round on that PR — for any reason, requested by anyone: new commits, a
  relayed finding, a decision the human made — is started by invoking `/kbabysit <n>`
  again, never by requesting a review yourself. That re-invocation is what decides between
  a paid round and a `kselfreview` pass, and it re-applies the budget and the stop rules
  from the last report onward. **If findings reach you with dispositions already attached
  — from the observer, from another session, from anywhere — do not act on the relay: run
  `/kbabysit <n>`** and let the triage happen where the stop rules live. A disposition
  arriving from outside is somebody else's triage with no scope judgement, no provenance
  and no budget behind it. Measured 2026-09-13: two executors took relayed dispositions
  and re-requested on instruction for 20 paid Copilot rounds after both loops had already
  stopped correctly (#61).
- Set the Decomposition row to `PR` with the PR link in its Evidence column, then
  `delivered` when merged. Nothing else to write: no handoff files, no completion
  report — the spec row, the PR, and git are the record.
