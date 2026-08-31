---
name: kissue
description: Deliver a bounded GitHub issue — a defect, chore, or narrowly scoped change whose desired outcome is already observable in the issue — as a PR with Closes #N. Use when the user points at an issue number; route feature-sized or materially ambiguous work to kspec instead.
argument-hint: "<issue-number>"
metadata:
  version: "2.0.0"
---

# kissue — bounded maintenance lane

```text
/kissue <issue-number>
```

Use this for defects, chores, and narrowly scoped changes whose desired outcome is already
observable in the issue. New product capabilities, consequential choices, multi-milestone
work, or issues without an independent definition of done belong in `/kspec`.

## Establish the contract

Fetch the full issue, linked PRs, discussion, and current repository state. Identify:

- the user-visible failure or bounded end state;
- existing reproduction or acceptance evidence;
- invariants and scope fences;
- whether the issue's stated facts still match the code.

If the contract is materially ambiguous or requires inventing product intent, stop and route
it to planning rather than silently deciding.

## Deliver

Own the implementation path. Reproduce the defect or unmet end state, change the code, add
useful regression coverage (the `test-quality` rule is the bar), and run the repository's
standing gates. Do not weaken an existing test or architecture contract.

Work on the current isolated branch when the harness already created one; otherwise create
an issue branch from the repository default. Commit coherently, push, and open a PR that
states the observable outcome and includes `Closes #<number>`.

Do not create a success-shaped PR around incomplete work. Record a concrete blocker when the
issue contract cannot be met.
