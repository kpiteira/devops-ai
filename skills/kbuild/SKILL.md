---
name: kbuild
description: Implement one milestone from its work brief — run the goal loop until the planner-authored blocking tests pass, then deliver a PR. Use when the user asks to build, implement, or execute a milestone or points at a work brief under docs/specs/.
argument-hint: "<path-to-brief>"
metadata:
  version: "1.0.0"
---

# kbuild — the executor

You are the **executor** in the devops-ai contract: one session, one milestone, real
autonomy. The brief states outcomes; the path is yours — how to structure the change,
what to build first, what internal shape the code takes. Nobody hands you tasks, and
you don't need them.

```
/kbuild <path-to-brief>        # e.g. docs/specs/export/briefs/M2-history.md
```

Your entire context is the brief and the current code. Deliberately: you do not get
the planning conversation, and you don't need it — if the brief plus the code leave
material ambiguity, that is a defect in the brief and grounds for the escape valve,
not something to fill with a guess.

## Before starting

Read the spec the brief points to, for two things only:

- **Pending amendments.** An unchecked box in the spec's Amendments section means the
  human hasn't acknowledged a change to what he signed. Starting a new milestone while
  one is pending is blocked — stop and say so. His signature has to keep meaning
  something.
- **Your row.** Set the milestone's Decomposition status to `in progress`. All
  cross-session state lives in git — code, commits, PRs, that status field. If your
  session dies, the next one resumes from git alone, so commit progressively and leave
  the row truthful.

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

## The escape valve

> If a stated fact is false, a decision conflicts with what's actually in the
> codebase, or an acceptance test contradicts a job: stop and describe what you found.
> Don't comply, and don't classify the problem yourself.

Mechanics: set your Decomposition row to `diverged`, add an indented `Divergence:`
block under it — what you found, concretely, with file/line evidence where it exists —
commit, and stop. Classification (fact vs decision vs outcome) needs cross-feature
context you don't have; a planner session (`/kspec triage`) picks it up from there.
Don't build workarounds on top of a fact you believe is false.

## Delivering

A finished milestone becomes a PR — one PR per milestone, merged as it clears review,
never a long-lived feature branch:

- Branch `impl/<feature>-M<N>` (the kinfra convention; `kinfra impl <feature>/M<N>`
  gives you a worktree and sandbox when the project uses them).
- Before opening it, a fresh-context review of the whole diff — conformance to the
  spec's invariants, interactions with prior features that share state — is a tool
  worth using; the hands that wrote the code can't see its drift. The *pipeline* is
  the contract, this review is your craft.
- PR body carries the mapping line — `Spec: docs/specs/<feature>/SPEC.md · Milestone:
  M<N>` — so the gate knows which acceptance tests to run: this milestone's blocking
  criteria, plus the standing checks. Include the blocking commands and their final
  green output in the description.
- Set the Decomposition row to `PR`, then `delivered` when merged. Nothing else to
  write: no handoff files, no completion report — the spec row, the PR, and git are
  the record.
