# ACP-NNN: <title>

**Feature/milestone:** `<feature>/<Mx>` · **Task:** `<id>` · **Date:** YYYY-MM-DD
**Status:** PROPOSED | ENDORSED | REFUTED | APPROVED | REJECTED

<!-- An Architecture Change Proposal is written at the moment of contact with a design
     that's wrong — by the agent that felt the friction. It is a proposal, not a license:
     the task that spawned it continues under the CURRENT architecture, and the change,
     if approved, lands as its own task with its own diff. Half a page, evidence-first. -->

## Friction evidence

<!-- What fought back, concretely: the contract or invariant you hit, the scenario the
     design doesn't fit, the exception you would otherwise request — quote the gate
     failure or the code. "I would have structured it differently" is not friction. -->

## What's wrong (design level)

<!-- The architectural decision that's wrong and why — not this task's inconvenience.
     Name the decision as the design doc states it. -->

## Proposed change

## Enforcement delta  (required — no delta, no ACP)

<!-- Exactly which contract changes: the invariant in test_invariants.py, the layering
     rule, the statement in ARCHITECTURE.md. An evolution that changes no contract is
     either a refactor (doesn't need an ACP) or a workaround (refused). -->

## Migration & debt

<!-- What existing code violates the new shape, and which named task/milestone pays it
     down. An unpriced "later" is the TODO(M4) pattern that never lands — name the
     milestone or ratchet it explicitly. -->

## Critique  (critique agent — fresh context, adversarial by default)

<!-- Verdict: ENDORSE / REFUTE / ENDORSE-WITH-CONDITIONS, with reasoning against each
     lens: Is this the design's problem or this task's inconvenience? Does it create a
     second way of doing something that already has a way? Does the enforcement delta
     actually close the loop, or loosen a contract without replacing it? Is the
     migration priced or hand-waved? -->

## Decision  (Karl)

<!-- APPROVED / REJECTED + date + conditions. Approved → schedule the change as its own
     task; amend docs and contracts in that task's diff, not this file. Refuted ACPs
     don't reach this section — they're logged in the handoff and the task proceeds
     under the current design. -->
