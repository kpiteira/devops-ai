# karchitect audit — implementation overview

**Design:** `../DESIGN.md` · **Architecture:** `../ARCHITECTURE.md` · **v1 baseline:** commit `1fdc2c9`

## Architecture in one screen (the substrate split)

The audit is a **bottom-up map-reduce over subagents**, built as a thin tested Python harness +
agent prompts + a SKILL.md that orchestrates them.

| Deterministic (Python, in `src/devops_ai/audit/`, TDD) | Agent-driven (prompts, validated by running on agent-memory) |
|---|---|
| inventory: walk + classify + partition | breakdown (file → structured FileBreakdown) |
| cluster: import/dependency graph | cluster naming + kind, synthesis, reconcile-judgment |
| coverage check (the J8 guarantee) | |
| artifact assembly (MAP/FINDINGS/COVERAGE/map.json) | |

The harness is where "every file accounted for" (J8) is *mechanically* guaranteed — the durable
core a model can't replace. The agents do the cognition.

## Milestones

| M | Goal | Stories (JTBDs owned) | Status |
|---|------|----------------------|--------|
| **M1** | Core bottom-up loop, top level: classify → break down every source file → cluster → N blind synthesizers → reconcile → high-level map + cross-cutting findings. Proven on agent-memory. | **J2** (findings), **J3** (confidence), **J4** (honesty), **J8** (exhaustive source coverage), **J1** (high-level map), **J7** (structured `map.json`/`FINDINGS.md`) | PLANNED |
| M2 | Progressive depth (drill-down levels) + full file-classification (tests/docs/config/generated handled). | (deepens J1, J8) | SKETCH |
| M3 | Drift pass (docs vs code-derived map) + confidence surfacing. | (deepens J4 — drift) | SKETCH |
| M4 | Refresh mode — re-run changed files + blast radius. | **J5** (freshness) | SKETCH |

J6 (scale) is exercised from M1 (agent-memory is the target), not owned by a milestone.

## Dependency graph

```
M1 (core loop)  ──►  M2 (depth + classification)  ──►  M3 (drift)  ──►  M4 (refresh)
```
Linear. Each milestone runs end-to-end on agent-memory and is validated against the v1 baseline.
M1 is the make-or-break: it tests the central bet (synthesizing from compressed breakdowns still
finds cross-cutting problems). If M1 fails its gates, the bottom-up approach is reconsidered before
M2 is planned.

## Branch strategy

One feature branch per milestone: `impl/karchitect-audit-m1`, off `main`. M1's harness lands in the
`devops_ai` package; the skill + prompts land in `skills/karchitect-audit/` (rewriting v1, which is
preserved at `1fdc2c9`).

## Human-action checkpoints

| When | Action | Why not automatable |
|------|--------|---------------------|
| M1 VALIDATION (gate 1) | **Karl reads the high-level map cold** and judges whether he understands agent-memory in ~5 min | "Karl-readable in 5 minutes" is inherently a human judgment — it's the whole point of the map |
| End of M1 | PR review + merge | Human gate |

## Note on VALIDATION (differs from the kplan default)

The audit has **no docker sandbox and no HTTP** — so the standard "ke2e-runner against a running
sandbox" path does not apply. M1's VALIDATION is a **direct run of the skill on agent-memory**, with
the generated artifacts checked against the v1 baseline and the five gates. It is a real end-to-end
run with observable outputs (the artifacts), just not containerized. Each milestone file states its
VALIDATION in those terms.
</content>
