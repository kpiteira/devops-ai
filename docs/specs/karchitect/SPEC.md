# karchitect audit — the map and its findings

**Status:** planning
**Signed off:** <!-- empty — restructured draft of 2026-10-04 after the Fable review; briefs and acceptance tests follow Karl's answers to E1–E3 and A1 -->

## Intent

Most of Karl's projects have no honest description of how they are actually built, and
nothing in devops-ai can produce one: every guardrail judges one change at a time against
rules someone already wrote. This feature gives devops-ai the whole-codebase view the rest
of its architecture work stands on. `/karchitect audit` reads every file of a Python
repository and writes a map of the system as it is (purpose, environment, components,
how they depend on each other) with evidence-backed findings about where it is unsound,
each carrying how many independent synthesizers reached it. It is the first of two
features: what the findings and the map then *govern* — ratified rules, planning against
the map, audits that recur — is `karchitect-loop`, planned once this feature's artifacts
exist on a real codebase.

## Outcomes

- `/karchitect audit` on a Python repository writes `MAP.md`, `map.json`, `FINDINGS.md`
  and `COVERAGE.md` under `docs/architecture/audit/<ISO-timestamp>/` in that repository,
  records the commit SHA it read, and modifies nothing else.
- `MAP.md` states the system's purpose, its environment, and its components with how they
  relate. No component is named after a package or module. Every source file belongs to
  exactly one component, tagged `feature` or `shared`. How many components a map may have
  is E2. `map.json` carries the same content, structured, including each component's
  member files.
- `COVERAGE.md` accounts for every tracked file as source, test, doc, config, or set aside
  with a stated reason. A run that would leave any file unaccounted for writes no artifacts
  and exits non-zero.
- Every finding states a problem (not a fact), its consequence, its evidence as `file:line`
  sites, its confidence as *k/N* independent synthesizers, and a draft severity
  `high | med | low`.
- `MAP.md` has a Disagreements section. When it is empty, the run's summary carries a
  perfect-agreement warning.
- On the planted-defect fixture repository (D8), every planted defect is reported as a
  finding whose evidence includes the planted sites.
- On agent-memory at the pinned SHA (A1), the run reports the ground-truth list. One item
  on it decides whether the bottom-up bet (D3) held: the scattered state writes, reported
  as a single finding with evidence sites in many files. v1's sampled audit found it in
  run-0 and lost it in run-1.
- **Human gate — Karl:** reading `MAP.md` cold, he can say what agent-memory does and name
  its parts in about five minutes. No test pins this; he records it at M1's delivery.

## Invariants

- karchitect never modifies a target repository's source code.
- No new runtime dependency in `pyproject.toml`.
- `/kspec`, `/kbuild`, `kbabysit` and the structural-gate rule are unchanged by this
  feature.
- The v1 artifacts under `docs/designs/architect-skill/` stay byte-identical: they are the
  baseline.

## Non-goals

- Everything `karchitect-loop` decides: ratifying findings into rules or refactor intents,
  `wont-fix` and finding identity across runs, the planner consulting the map, deltas
  between audits, when audits recur, and anything that checks a PR against the map.
- Running a refactor.
- Reimplementing lint-catchable checks (layering, file budgets, duplication) inside the
  audit; those are the structural gates' job.
- Non-Python targets. The method is language-agnostic; the edge extraction is not.
- C4 levels below components: container views, sequence diagrams, rendered drill-down.
- A separate docs-versus-code drift pass (D1 covers drift as a finding category).

## Discovered context

- **v1 (May 2026)** — `docs/designs/architect-skill/INTENT.md`: four skills and a five-layer
  program; only L1 was built (`skills/karchitect-audit/`, v0.2.0, three blind modelers
  plus a synthesizer). It ran twice on agent-memory. Run-1 recorded `Git SHA: unknown`
  (`audit/run-1/01-system-context.md:4`). Its catalog is F001–F011; three of those
  (F005, F007, F010) are README-versus-code drift the modelers found without a drift pass.
  Per DISTILLATION, the full v1 is preserved at commit `1fdc2c9`.
- **The scattered state writes** — run-0's Surprise 1: "There is no `MemoryStore` — file
  writes are scattered across ~40 files" (`audit/run-0/01-system-context.md:106`). Run-1
  missed it entirely (`audit/FINDINGS.md:52`). INTENT.md counts "420+ direct write sites
  bypassing the nominal gateway".
- **Component count** — v1 targeted 4–7 components. Run-1 produced 10 and kept them,
  because two modelers independently separated `BriefingComposer`, `ActionGate` and
  `Sentinel` (`run-1/01-system-context.md:106`, `audit/FINDINGS.md:73`).
- **DISTILLATION (2026-06-03)** — keep: separate "what the system is" from "what's wrong";
  problem-plus-consequence findings pinned to `file:line`; independent readers as a
  confidence signal; the 5-minute bar. Drop: the rigid layer program, scripted
  orchestration, the four-skill split.
- **karchitect-v2** — `docs/designs/karchitect-v2/`: the bottom-up design this spec keeps,
  plus an M1–M4 plan in the pre-v2-contract task format. No harness exists on any branch,
  and nothing outside `skills/karchitect-audit/` references the skill. This spec supersedes
  that plan and keeps its data shapes (`FileBreakdown`, `Edge`, `Component`, `Finding`,
  `HighLevelMap`) as the briefs' starting Surface.
- **Precedent for an in-skill script** — `skills/kpage/build.py` runs with
  `uv run --script` from the skill directory; `make check` lints and type-checks `src/`
  and `tests/` only.
- Acceptance tests live in `tests/acceptance/karchitect/`; the directory name must be
  importable, so no hyphens. `check_contract_integrity.py` guards `tests/acceptance/**` and
  `docs/specs/*/briefs/*.md`.

## Decisions

- **D1** — The map is derived from code only. A doc claim the code contradicts is a finding
  of category `drift`. *Rejected:* docs as input (they are stale; F005, F007 and F010 are
  exactly that); a separate drift pass (v1 got drift findings without one).
- **D2** — Every file is examined and classified, and a gap fails the run. *Rejected:*
  sampling flows as the coverage model. Sampling is how v1 lost the scattered writes
  between run-0 and run-1.
- **D3** — Bottom-up: each source file is broken down once into structured edges (`import`,
  `call`, `reads_state`, `writes_state`, each with a site), and N blind synthesizers build
  the map from the breakdowns. `import` and `call` edges come from the stdlib `ast`; state
  edges come from the breakdown agent. *Rejected:* reading every file N times (cost);
  one synthesizer (no confidence signal).
- **D4** — Single component membership with kind `feature | shared`. A file straddling two
  feature components becomes a coupling finding. *Rejected:* multi-membership, which
  smooths over the strain the audit exists to show.
- **D5** — Findings within one run are deduplicated on category plus overlapping evidence
  sites; *k* counts the synthesizers that reported the merged finding. N = 3, matching v1.
  *Rejected:* v1's A1–D7 dimension taxonomy. Identity *across* runs is `karchitect-loop`'s.
- **D6** — Deterministic work (inventory, partition, coverage, dedup, schema validation) is
  tested Python; cognition (breakdown, naming, synthesis, reconciliation) is prompts; the
  skill states goals and gates, and the model orchestrates the fan-out. *Rejected:* v1's
  scripted orchestration protocol.
- **D7** — One skill, `/karchitect`; this feature ships its `audit` mode and replaces
  `skills/karchitect-audit/`. *Rejected:* one skill per job, the v1 split DISTILLATION
  dropped.
- **D8** — Ground truth is a planted-defect fixture repository under
  `tests/acceptance/karchitect/fixtures/`: a small Python package with a god-module, state
  writes scattered across files, a file straddling two features, a doc claim the code
  contradicts, and a `shared` utility. Deterministic harness behavior (coverage, partition,
  schema, artifact layout) is graded by deterministic blocking tests on it. How recovery is
  graded is E1. *Rejected:* agent-memory as the only target (a private repository with no
  recorded SHA, so no reproducible baseline).

## Decomposition

| Milestone | Brief | Jobs | Depends on | Status | Evidence |
|-----------|-------|------|------------|--------|----------|
| M1 — The map | briefs/M1-map.md | J1 a map of how the system is built, J2 every file accounted for, J3 the map as structured data | — | pending | — |
| M2 — The findings | briefs/M2-findings.md | J4 problems pinned to code with consequences, J5 how much to trust each one | M1 | pending | — |

M1 runs on the fixture and on agent-memory and ends with Karl's five-minute read. M2 adds
findings and confidence, and is where the scattered-writes criterion is measured.

## Escalations — Karl's, options without recommendation

- **E1 — May a blocking command invoke a model?** This decides how recovery (planted
  defects, agent-memory's ground truth) is graded, and every later spec that grades a skill
  inherits the answer. (a) Yes: the blocking command runs the audit headless on the fixture
  and asserts recovery. Each run costs planner-tier tokens, and its result can vary between
  runs on the same commit. (b) No: blocking commands stay deterministic. Recovery is graded
  by a labeled integration-level test whose measured baseline the brief records, as the
  contract allows when the live stack cannot exercise the job. The executor's runs and
  your read are the evidence; the blocking command does not re-run the model.
- **E2 — What may a component be?** This is the map's product semantics. (a) A hard bound:
  4–7 components; a larger system is mapped as 4–7 at the top level. (b) A soft bound: 4–7
  is the target, and each component past seven carries a stated reason in `MAP.md`.
  (c) No count: components are bounded only by D4 and the concept-noun rule. On
  agent-memory, (a) forces merges two modelers argued against in run-1, (b) admits run-1's
  10 with three reasons, and (c) admits any number.
- **E3 — The audit's harness surface.** (a) A third console script, `karchitect`, in the
  `devops_ai` package, like `ksecret`: one more entry point after `uv tool install`,
  covered by `make check`. (b) A `kinfra` subcommand: no new entry point, and kinfra's
  surface grows (secret-providers held it fixed as that feature's invariant). (c) Scripts
  in the skill directory run with `uv run --script`, like `kpage/build.py`: nothing to
  install, and outside `make check`'s `src/` and `tests/` scope unless that scope grows.

## Assumptions

- A1 — agent-memory is audited at the last commit on or before 2026-05-15, the v1 audit
  date; the SHA is pinned from that repository's log during planning. The ground-truth
  list is F001 (`services.py` god-module), F002 (scheduler doing approval and channel
  routing), and the scattered state writes; Karl confirms it by hand rather than the audit
  under test deciding which findings still hold.
- A2 — The audit runs on the planner tier and states its model first, as `/kspec` does.
- A3 — `skills/karchitect-audit/` is deleted when M1 lands; `docs/designs/karchitect-v2/`
  stays as design history.

## Amendments
