# karchitect — systemic architecture guardrails

**Status:** planning
**Signed off:** <!-- empty — draft of 2026-10-04 for Karl's reaction; briefs and acceptance tests not yet written -->

## Intent

Every guardrail devops-ai has today judges code one change at a time: the structural
gates check a tree against contracts someone already wrote, `kbuild`'s fresh-context
review reads one milestone's diff, `kbabysit` reads one PR's review rounds. None of them
sees the codebase as a whole or how it moves over time, which is where architectural rot
lives: a dozen locally sound changes that together give a concept a second home or route
around the one gateway. karchitect supplies that missing view. It derives an honest map of
how a codebase is actually built, with evidence-backed findings about where it is unsound,
and closes the loop the May and June designs left open: a ratified finding becomes an
enforced rule or a refactor intent, the planner consults the map before deciding where new
work belongs, and successive audits show what moved. Drift that has been diagnosed once
cannot quietly recur.

## Outcomes

- `/karchitect audit` on a Python repository writes `MAP.md`, `map.json`, `FINDINGS.md` and
  `COVERAGE.md` under `docs/architecture/audit/<ISO-timestamp>/` in that repository and
  touches nothing else.
- `MAP.md` states the system's purpose, its environment, and 4–7 components named as concept
  nouns (not package names), with how they relate. A reader who has never opened the code
  can name the parts within five minutes. Every source file belongs to exactly one component,
  tagged `feature` or `shared`.
- `COVERAGE.md` accounts for every tracked file: source, test, doc, config, or set aside
  with a stated reason. A run that leaves any file unaccounted for fails instead of writing
  artifacts.
- Every finding states a problem (not a fact), its consequence, its evidence as `file:line`
  sites, its confidence as *k/N* independent synthesizers, a draft severity, and a status.
  The map carries a non-empty Disagreements section; a run where all synthesizers agree
  says so as a warning.
- On the planted-defect fixture repository every planted defect is recovered. On
  agent-memory (A1) the run recovers the v1-known `services.py` god-module (F001), the
  scheduler's approval routing (F002), and the scattered state-write pattern.
- Ratifying a finding produces exactly one of three outcomes: a structural-gate contract that
  fails on any new violation, with existing violations frozen in a ratchet; a refactor
  intent that `/kspec` accepts as its input dump; or `wont-fix`, after which the finding is
  not raised again while its evidence is unchanged.
- In a repository with an audit, `/kspec plan` names the owning component of every concept
  the feature touches in Discovered context, and escalates to the human options-first when
  the feature would add a component or give an existing concept a second home. When the
  audit's SHA is behind HEAD, the spec says how far behind.
- An audit run with an earlier audit present reports the difference between them: findings
  new, resolved and persisting; components added, removed or merged; and the change in
  cross-component edges.

## Invariants

- karchitect never modifies a target repository's source code.
- Structural-gate semantics are unchanged (`rules/structural-gates.md`): a ratified finding
  may add a contract or freeze a ratchet at its current size; nothing widens a contract
  or raises a ratchet.
- `/kspec`'s writing rule, Assumptions and per-item sign-off are unchanged. The map adds
  to what the planner investigates and escalates; it decides nothing on its own.
- The glossary stays a record of what Karl has been taught, not an enforced vocabulary
  law. Component names do not become glossary entries automatically.
- No new runtime dependency in `pyproject.toml`.
- The v1 artifacts under `docs/designs/architect-skill/` stay byte-identical: they are the
  baseline.

## Non-goals

- Running a refactor. A refactor intent goes through `/kspec` → `/kbuild` like any feature.
- A per-PR LLM architecture reviewer (see D7).
- Reimplementing lint-catchable checks (layering, file budgets, duplication) inside the
  audit. Those belong to the structural gates, which M2 feeds.
- Non-Python targets. The method is language-agnostic; the edge extraction is not.
- C4 levels below components: container views, sequence diagrams, rendered drill-down.
  `map.json` carries component → file membership; nothing renders it further.
- Scheduling audits automatically.
- A prose `ARCHITECTURE.md` kept current by hand (E1 decides what persists).

## Discovered context

- **v1 (May 2026)** — `docs/designs/architect-skill/INTENT.md`: four skills (audit, map,
  design, review) and a five-layer L1→L5 program. Only L1 was built:
  `skills/karchitect-audit/` (v0.2.0, three blind modelers plus a synthesizer). It ran twice
  on agent-memory (`audit/run-0`, `audit/run-1`). Run-1's `FINDINGS.md` lists F001–F011 with
  convergence tags. Three findings are README-versus-code drift (F005, F007, F010), which the
  modelers surfaced without a dedicated drift pass. Per DISTILLATION, the full v1 is
  preserved at commit `1fdc2c9`.
- **DISTILLATION (2026-06-03)** — keep: separate "what the system is" from "what's wrong";
  problem-plus-consequence findings pinned to `file:line`; independent readers as a
  confidence signal; the 5-minute bar. Drop: the rigid layer program, scripted
  orchestration, the four-skill split. "Build the audit first, on agent-memory."
- **karchitect-v2** — `docs/designs/karchitect-v2/`: a bottom-up design (classify every file →
  per-file breakdown with structured edges → cluster → N blind synthesizers → reconcile),
  plus an M1–M4 plan in the pre-v2-contract task format (nine tasks with hour estimates).
  M1 is marked PLANNED, M2–M4 SKETCH. No harness exists on any branch (`src/devops_ai/audit`
  is absent everywhere), and nothing outside `skills/karchitect-audit/` references the
  skill. This spec supersedes that plan and keeps its data shapes (`FileBreakdown`,
  `Edge`, `Component`, `Finding`, `HighLevelMap`) as the briefs' starting Surface.
- **What landed since, and covers the local half** — v2 contract (2026-08-24);
  `rules/structural-gates.md` with `templates/test_invariants.py` (file budgets, module
  shape, layering, pattern uniqueness, test honesty, shrink-only ratchets, three sign-off
  requests = escalate); `/kspec` turns durable invariants into architecture tests;
  `/kbuild` runs fresh-context review against the spec's invariants; `kbabysit` classifies
  findings isolated/systemic; CI runs `.devops-ai/check_public_surface.py` (advisory).
- **Lost in the v2 rewrite** — DISTILLATION's "stay clean" counted on a kbuild
  *Architecture Reconciliation* step. `skills/kbuild/SKILL.md` no longer has one, so nothing
  keeps any architecture description current today.
- **Tension with the contract** — CONTRACT.md rejects standalone decision logs ("they
  metastasize"). Persisting `wont-fix` statuses across audit runs is a small decision log
  unless it is promoted into something that enforces it (E5).
- devops-ai itself has `tests/architecture/` with feature-specific tests but no copy of the
  `test_invariants.py` starter. `make test-arch` runs whatever is there.
- Acceptance-test directories must be importable: `tests/acceptance/karchitect/`.
  `check_contract_integrity.py` guards `tests/acceptance/**` and `docs/specs/*/briefs/*.md`.

## Decisions

- **D1** — The map is derived from code only. Docs never feed it; a doc claim the code
  contradicts is a finding of category `drift`. *Rejected:* docs as input (they are stale;
  v1 F005/F007/F010 are exactly that); a separate drift pass (v1 got drift findings without
  one).
- **D2** — Exhaustive coverage by classification: every file examined and bucketed, and a
  gap fails the run. *Rejected:* sampling five flows as the coverage model. Larson's method
  remains how a synthesizer reads, not what gets covered.
- **D3** — Bottom-up: each source file is broken down once into structured edges (`import`,
  `call`, `reads_state`, `writes_state`, each with a site). Independence is applied at
  synthesis, with N blind synthesizers working from the breakdowns. *Rejected:* reading
  every file N times (cost for little gain); a single synthesizer (no confidence signal).
- **D4** — Single component membership with kind `feature | shared`. A file straddling two
  feature components becomes a coupling finding. *Rejected:* multi-membership (it smooths
  over the strain the audit exists to show).
- **D5** — Finding shape per Outcomes. Severity is a draft `high | med | low` that Karl
  ratifies. Identity across runs is category plus overlapping evidence sites. *Rejected:*
  v1's A1–D7 dimension taxonomy.
- **D6** — Deterministic work (inventory, partition, coverage, dedup, identity, delta,
  schema validation) is tested Python. Cognition (breakdown, naming, synthesis,
  reconciliation) is prompts. The skill states goals and gates, and the model orchestrates
  the fan-out natively. *Rejected:* v1's scripted orchestration protocol.
- **D7** — No per-PR architecture reviewer. Systemic judgment sits at planning time (M3) and
  between audits (M4). Per-PR coverage stays the structural gates plus `kbuild`'s
  fresh-context review. *Rejected:* a per-PR architect agent, which sees a diff, not a
  trajectory, and judges against a description that drifts.
- **D8** — One skill, `/karchitect`, with modes (`audit`, `ratify`, `delta` if separate
  from audit), replacing `skills/karchitect-audit/`. *Rejected:* one skill per job (the v1
  split DISTILLATION dropped).

## Decomposition

| Milestone | Brief | Jobs | Depends on | Status | Evidence |
|-----------|-------|------|------------|--------|----------|
| M1 — Audit: map + findings | briefs/M1-audit.md | J1 map in minutes, J2 findings pinned to code, J3 confidence, J4 coverage + disagreements, J5 machine-readable output | — | pending | — |
| M2 — Ratify: findings become guardrails | briefs/M2-ratify.md | J6 finding → gate contract + ratchet, J7 finding → refactor intent / wont-fix | M1 | pending | — |
| M3 — Plan against the map | briefs/M3-plan-against-map.md | J8 owning component named, J9 second home / new component escalated | M1 | pending | — |
| M4 — Delta between audits | briefs/M4-delta.md | J10 what moved since the last audit | M1 | pending | — |

M1 is make-or-break: if synthesizing from breakdowns does not recover the known findings,
the bottom-up bet is reconsidered before M2–M4 are briefed. M2, M3 and M4 are independent
of each other.

## Escalations — Karl's, options without recommendation

- **E1 — What persists between audits.** (a) Nothing but the audit directories: the map is
  re-derived on demand, and the planner runs or reuses an audit by SHA. (b) A committed
  `map.json` that every milestone PR keeps current, which puts an architecture-reconciliation
  obligation back on `/kbuild`. (c) A committed `map.json` refreshed incrementally (changed
  files plus blast radius) when it falls behind HEAD. *Consequences:* (a) costs a full run
  whenever the map is stale and keeps no prose to drift; (b) keeps the map fresh at the cost
  of an obligation the v2 rewrite dropped; (c) adds v2's refresh mode as a fifth milestone.
- **E2 — How M1 is graded.** (a) The blocking command invokes the skill headless on the
  planted-defect fixture and asserts recovery. (b) Blocking tests grade a committed run's
  artifacts (schema, coverage, Disagreements, recovery against ground truth), and the run is
  an executor action. (c) Deterministic harness tests block; recovery on the fixture and
  agent-memory is a labeled integration-level test plus Karl's 5-minute read.
  *Consequences:* (a) tests the skill itself but is token-costly and non-deterministic;
  (b) is deterministic but grades a run, not the skill; (c) is cheapest and the most honest
  about what a test can pin, and leans hardest on the human gate.
- **E3 — Where a ratified rule lands.** (a) `/karchitect ratify` writes the contract and
  ratchet into the target's `tests/architecture/` on a branch, reviewed as a normal PR.
  (b) Ratify emits a proposal that the next `/kspec` session turns into a spec invariant
  plus architecture test. *Consequences:* (a) is one step, but contracts can arrive without
  a spec; (b) keeps "contracts come from planning" (structural-gates rule) at the cost of
  one more session per rule.
- **E4 — Harness surface.** (a) A third console script, `karchitect`. (b) A `kinfra`
  subcommand. (c) Scripts inside the skill directory, invoked by path. *Consequences:*
  (a) mirrors `ksecret`; (b) grows kinfra, which secret-providers held fixed; (c) avoids a new
  install step but leaves the harness outside the package's test and type gates.
- **E5 — Where `wont-fix` lives.** (a) A small accepted-findings file keyed by finding
  identity, read by every run. (b) Only what can be enforced persists, as a ratchet or
  allowlist entry; anything else is re-raised every run. (c) It is carried forward by M4's
  delta from the previous audit and expires when its evidence sites change. *Consequences:*
  (a) is a decision log in miniature, which the contract rejects; (b) is pure but noisy;
  (c) ties E5 to M4.

## Assumptions

- A1 — agent-memory is audited at the SHA run-1 used, so the v1 findings are ground truth.
  If it has since been refactored, current HEAD is used with only still-true findings.
- A2 — A planted-defect fixture repository (a small Python package with a god-module,
  scattered state writes, a straddling file, a doc claim the code contradicts, and a
  `shared` utility) lives under `tests/acceptance/karchitect/fixtures/` as ground truth.
- A3 — N = 3 blind synthesizers, matching v1.
- A4 — `import` and `call` edges are extracted deterministically with the stdlib `ast`;
  `reads_state` / `writes_state` come from the breakdown agent.
- A5 — The audit runs on the planner tier and states its model first, like `/kspec`.
- A6 — `skills/karchitect-audit/` is deleted when M1 lands; `docs/designs/karchitect-v2/`
  stays as design history.
- A7 — In M3, the map informs the planner's escalation judgment, the way the public-surface
  report does. It is not a hard gate on sign-off.

## Amendments
