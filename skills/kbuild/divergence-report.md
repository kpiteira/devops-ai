# Divergence - <feature>/<milestone> - YYYY-MM-DD

**Brief:** `<path>`  
**Blocking command:** `<command>`  
**Milestone status:** `diverged`

<!-- Not for a wrong annotation on a requirement you can build unambiguously — that is
a fact-correction, recorded under "Facts I corrected" in the PR (kbuild). This report is
for a false fact that changes what to build, a decision the code contradicts, or a test
that contradicts its job. -->

## What contradicts the contract

<Quote the false fact, conflicting decision, or job/test contradiction.>

## Evidence

<Current code, command output, or observable behavior — from the running stack, on
main, not only your branch. Keep this reproducible.>

## Why implementation stopped

<Explain why proceeding would require a workaround, self-grading, a widened security
boundary, or an unowned product decision.>

## Planner resolution

<!-- Filled only by kspec triage. Classification: false fact / untenable model decision /
wrong job or outcome. Link the amendment and human acknowledgement when required. -->
