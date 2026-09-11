# Feature close - <feature>

**Intent spec:** `<path>`  
**Feature diff:** `<base>...<head or merged PR set>`  
**Pass:** first | second (confirming corrective milestones)  
**Verdict:** CONFORMS | CORRECTIVE MILESTONES REQUIRED | RETURN TO HUMAN

## Intent assessment

<Does the combined behavior deliver the value stated in Intent? Be concrete and brief.>

## Adversarial angle

<Which lifecycle was driven to its end, from what angle the blocking tests did not take,
and what it showed. On a second pass: a different angle from the first.>

## Material findings

| Finding | Intent / outcome / invariant affected | Evidence | Resolution |
|---------|---------------------------------------|----------|------------|

## Corrective milestones

<Links to newly planner-authored briefs and blocking tests, or "None". When present the
spec stays `closing` and a second fresh close confirms before archiving.>

## Outside the outcomes

<What this review saw that is not this feature's drift — a gap the spec never claimed,
a footgun next door. Roadmap notes, not findings; each one line.>

## Acceptance-test disposition

| Milestone | Scoped test | Promote to (e2e / integration / unit / drop) | Human decision |
|-----------|-------------|----------------------------------------------|----------------|

## Archive sweep

<`grep` of the repository for the spec path before the move; every outside reference
that followed.>
