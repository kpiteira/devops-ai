# Outcome Contracts

Be rigid about outcomes and silent about paths.

The human owns product intent, acceptable trade-offs, and consequential hard-to-reverse
decisions. The planner (`/kspec`) turns that intent into a signed spec, vertical milestone
briefs, and blocking acceptance tests. The executor (`/kbuild`) owns the implementation path.

## Contract boundaries

- A feature is the unit the human plans.
- A milestone is a user-visible vertical slice and the unit of delivery.
- A work brief specifies the milestone without prescribing implementation.
- Tasks are not a framework concept.

Every job in a brief maps to a planner-authored blocking test written before implementation.
The executor never authors or edits its own grader. Executor-written tests are implementation
tools, not the delivery contract.

Briefs contain facts, decisions, testable end states, and explicitly labeled human
directives. Unlabeled ordered steps, file lists, or internal design instructions are process
leakage.

## Enforcement

The kinfra-generated CI guard (`.devops-ai/check_contract_integrity.py`, run from the PR's
base commit) rejects changes to work briefs or acceptance tests on every branch except
`spec/*` and `replan/*`. Planning sessions therefore work on `spec/<feature>` or
`replan/<feature>` branches; executor sessions on `impl/<feature>-M<N>`. A PR that touches
the guard or the workflow from an unknown branch is flagged for review.

## Escape valve

If a stated fact is false, a decision conflicts with reality, or a blocking test contradicts
its job, execution stops with evidence. The executor does not comply, work around it, edit
the test, or classify the problem. A planner session triages it with cross-feature context.

## Durable state

Code, tests, the intent spec's status table, amendments, and divergence reports are the
complete cross-session state. Chat history, handoff rituals, and implementer claims are not.
