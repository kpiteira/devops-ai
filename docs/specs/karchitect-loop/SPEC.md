# karchitect loop — findings become guardrails

**Status:** planning — briefed after `karchitect` (the audit) is delivered
**Signed off:** <!-- empty — this spec holds the questions the loop turns on; it gains milestones, briefs and tests once a real map exists to decide them against -->

## Intent

An audit by itself is a snapshot that starts going stale the next day. This feature makes
what the audit finds govern the code that follows it. A finding Karl ratifies becomes an
enforced rule or a refactor intent, the planner places new work against the map, and
audits recur on an event that already happens, so drift between them becomes visible.
How far this goes depends on E1: a drift class that compiles to an import or pattern rule
can be stopped from recurring; one that needs judgment (a concept getting a second home,
a gateway bypassed in spirit) is either caught per PR or surfaced at the next audit.

## Outcomes (provisional — fixed by E1–E6)

- Ratifying a finding produces a structural-gate contract with existing violations frozen
  in a ratchet, a refactor intent `/kspec` accepts as its input, or `wont-fix`, recorded
  as E5 decides.
- An audit runs on the event E3 names, and when an earlier audit exists, it reports what
  moved: findings new, resolved and persisting; components added, removed or merged; the
  change in cross-component edges.
- `/kspec plan`, in a repository with an audit, states which component owns each concept
  the feature touches, and escalates to Karl options-first when the feature would add a
  component or give an existing concept a second home. Where that placement lands is E6.
- Between audits, a change is checked for systemic drift as E1 decides.

## Invariants

- karchitect never modifies a target repository's source code; rules reach
  `tests/architecture/` only as E4 decides.
- Structural-gate semantics are unchanged (`rules/structural-gates.md`): a ratified finding
  may add a contract or freeze a ratchet at its current size; nothing widens a contract
  or raises a ratchet.
- `/kspec`'s writing rule, Assumptions and per-item sign-off are unchanged.
- The glossary stays a record of what Karl has been taught, not an enforced vocabulary
  law. Component names do not become glossary entries automatically.

## Non-goals

- Running a refactor: a refactor intent goes through `/kspec` → `/kbuild` like any feature.
- Re-deciding anything the audit feature signed (map shape, finding shape, coverage).

## Discovered context

- `/kbuild`: "Your entire context is the brief and the current code"
  (`skills/kbuild/SKILL.md:22`). Its fresh-context review checks "conformance to the spec's
  invariants" (`:110-112`). A spec's Discovered context reaches neither.
- CONTRACT.md's second principle: "every mechanism must either run automatically or attach
  to an event that already happens. Nothing may rely on anyone's ongoing discipline."
  (`docs/designs/v2-contract/CONTRACT.md:15`). The May and June designs were never used
  (DISTILLATION).
- CONTRACT.md, "No standalone decision log": a decision that outlives its feature is
  promoted into an artifact that enforces it (a spec invariant, an architecture test, a
  glossary note).
- `rules/structural-gates.md`, "Where the contracts come from": from planning, each durable
  structural decision in a feature's intent spec lands as a machine check.
- DISTILLATION's "stay clean" relied on a `/kbuild` *Architecture Reconciliation* step; the
  v2 rewrite of `skills/kbuild/SKILL.md` has none, so nothing keeps an architecture
  description current today.
- karchitect-v2's refresh mode re-derives changed files plus their blast radius
  (`docs/designs/karchitect-v2/ARCHITECTURE.md:118-122`) and lists bounding the blast
  radius as an open risk.
- AGENTS.md: a change to the contract's mechanics belongs in CONTRACT.md or
  `docs/EVOLUTIONS.md`, not only in a skill.

## Escalations — Karl's, options without recommendation

E1 comes first: E2 and E6 follow from what checks a change between audits.

- **E1 — What checks a change for systemic drift between audits.** (a) Today's structural
  gates and `/kbuild`'s fresh-context review, unchanged; drift outside any written rule
  surfaces at the next audit. No per-PR cost; a judgment-only drift class can stand until
  then. (b) A structural gate generated from `map.json`: a new cross-component dependency
  absent from the map's relationships, or a new source file with no component, fails
  `make check` until the same PR updates the map. Deterministic on every PR; requires a
  committed map that changes whenever the architecture legitimately does. (c) A per-PR
  reviewer agent given `map.json` as its reference, reporting systemic findings on the PR.
  Can judge cohesion, which no rule expresses; one model call per PR, with a
  non-deterministic verdict.
- **E2 — What persists between audits.** (a) The audit directories only; the map is
  re-derived when needed. A full planner-tier run each time it is stale; nothing between
  audits holds a current map, so E1(b) and E1(c) have no reference. (b) A committed
  `map.json` updated by every PR that changes the architecture. Current at all times; each
  such PR carries the update, as `/kbuild`'s former Architecture Reconciliation step did.
  (c) A committed `map.json` refreshed incrementally from changed files and their blast
  radius (karchitect-v2's refresh mode). Cheaper than a full run; correct only as far as
  the blast radius is bounded correctly.
- **E3 — The event an audit attaches to.** (a) `/kspec plan`, when the map is behind HEAD:
  every planning session pays for freshness, and the map is current when placement is
  decided. (b) `/kspec close`, with the delta part of the feature-close review: one audit
  per feature, landing where drift is already reviewed, and a map up to one feature behind
  at planning. (c) Both. On-demand only is excluded by CONTRACT.md's second principle.
- **E4 — Where a ratified rule lands.** (a) `/karchitect ratify` writes the contract and
  ratchet into the target's `tests/architecture/` on a branch, reviewed as a normal PR: one
  step, and the contract arrives without a spec recording it. (b) Ratify emits a proposal
  the next `/kspec` session turns into a spec invariant plus architecture test: the
  contract arrives through a spec, as the structural-gates rule describes, at one more
  planner session per rule.
- **E5 — Finding identity across runs, and what `wont-fix` means.** Identity: (i) category
  plus overlapping evidence sites, the audit's within-run dedup key, so a finding is "new"
  when its code moves; or (ii) category plus the components it touches, so it survives
  moves inside a component. Persistence: (a) a file of accepted findings keyed by
  identity, read by every audit; a standing record of decisions, the form CONTRACT.md's
  "No standalone decision log" addresses. (b) Only what compiles to a ratchet or allowlist
  entry persists; a `wont-fix` that compiles to no rule is reported again in every audit.
  (c) The delta carries `wont-fix` forward until the finding's identity changes; ratify
  then depends on the delta.
- **E6 — Whether the planner's placement binds the executor.** (a) It goes in the spec's
  Discovered context: it informs Karl's sign-off and does not reach `/kbuild`. (b) It goes
  in the brief's Invariants, which the fresh-context review checks. (c) It becomes a
  structural-gate contract, which requires E1(b). Any of the three changes what a planner
  session does in every repository with an audit; per AGENTS.md, that change lands in
  CONTRACT.md's "How the human keeps up" as Karl's directive.

## Assumptions

- A1 — The loop's milestones are ratify, plan against the map, and the delta; their order
  and dependencies follow from E1, E3 and E5 (under E5(c), ratify depends on the delta).

## Amendments
