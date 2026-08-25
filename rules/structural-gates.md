# Structural Gates

Code structure is a gated quality dimension, exactly like lint and tests. Spaghetti passes
every functional gate — it type-checks, each copy has passing tests, the feature works. These
gates exist because the agents writing code have no other signal that structure is degrading,
and a human reading classes is not a scalable sensor.

## The gate

Every project carries a structural-invariants gate, run as part of the quality checks
(in `make check`, so pre-commit and CI both enforce it). For Python projects that's
`tests/architecture/test_invariants.py` (starter template below); non-Python projects
encode the same contracts with their stack's tooling (e.g. dependency-cruiser or ts-arch
for TypeScript layering, ESLint rules for pattern caps). The gate encodes the
machine-checkable half of the project's architecture:

- **File budgets** — no source file beyond the configured line cap (default 400)
- **Module shape** — caps on classes/dataclasses per module (a module quietly collecting
  result types is how god-files start)
- **Layering contracts** — which packages may import which ("domain never imports api")
- **Pattern uniqueness** — one mechanism per job ("no `*Result` dataclass outside
  `results/`", "exactly one router base")
- **Test honesty** — patch-density caps and no first-party patching (per the
  `test-quality` rule: testing theatre is a structure problem; a mock-welded suite
  resists every refactor the other gates demand)
- **Ratchets** — frozen allowlists for violations that pre-date the gate

A starter lives at `templates/test_invariants.py` (devops-ai). Thresholds and contracts
are configured in the copied file's own Configuration block — once copied into
`tests/architecture/`, it is project-owned, versioned with the code it constrains.

## The non-negotiables

- **A structural gate failure is fixed by changing the code — never by editing the
  threshold, the contract, or the allowlist.** Widening anything requires Karl's explicit
  sign-off, recorded as an amendment in the feature's spec.
- **Ratchets only shrink.** The allowlist freezes the violations that existed when the gate
  was introduced; new code meets the bar immediately. When a legacy file comes into
  compliance, its entry is removed (the test enforces this) so it can't regress.
- **Three sign-off requests against the same contract is a design signal, not a third
  exception.** The contract is probably wrong — that's the escape valve: escalate to a
  planner session (`/kspec triage`) so it gets decided, not routed around.

## Where the contracts come from

From planning: each durable structural decision in a feature's intent spec (its
Invariants) should land as a machine check here — enforced structure is run, not read,
so it can't go stale, and "locally better but violates a boundary" fails CI instead of
requiring anyone's judgment. A decision that can't be expressed as a machine check stays
a spec invariant the reviews carry — an explicit choice, recorded, never a default.
