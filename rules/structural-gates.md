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
- **Test honesty** — patch-density caps and no first-party patching (per the `tdd` rule:
  testing theatre is a structure problem; a mock-welded suite resists every refactor the
  other gates demand)
- **Ratchets** — frozen allowlists for violations that pre-date the gate

A starter lives at `templates/test_invariants.py` (devops-ai). Thresholds and contracts
are configured in the copied file's own Configuration block — once copied into
`tests/architecture/`, it is project-owned, versioned with the code it constrains.

## The non-negotiables

- **A structural gate failure is fixed by changing the code — never by editing the
  threshold, the contract, or the allowlist.** Widening anything requires Karl's explicit
  sign-off in the conversation, recorded in the handoff.
- **Ratchets only shrink.** The allowlist freezes the violations that existed when the gate
  was introduced; new code meets the bar immediately. When a legacy file comes into
  compliance, its entry is removed (the test enforces this) so it can't regress.
- **Three sign-off requests against the same contract is a design signal, not a third
  exception.** The contract is probably wrong — write an ACP (see kbuild) so it gets
  decided, not routed around.

## Where the contracts come from

From the architecture: each enforceable decision in ARCHITECTURE.md should name its check
here. A decision that can't be expressed as a machine check is enforced as a named lens in
kbuild's structural review instead — but that's an explicit choice, recorded in the doc,
not a default.
