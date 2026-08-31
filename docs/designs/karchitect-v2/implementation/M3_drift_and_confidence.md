---
design: docs/designs/karchitect-v2/DESIGN.md
architecture: docs/designs/karchitect-v2/ARCHITECTURE.md
---

# M3 — Drift pass + confidence surfacing  ·  SKETCH — re-plan before build

**Goal:** after the code-derived map exists, compare the docs against it to produce **drift
findings** ("README says X, code does Y"), and surface the confidence/disagreement signal cleanly in
the output.

**Deepens:** J4 (honesty — drift + confidence), J7 (structured output for the pipeline).

**Key tasks (sketch):**
- Drift checker: a pass that reads docs (`.md`) as *claims* and checks each against the code-derived
  map/breakdowns → drift findings (e.g. the v1 "CLI is a thin client; it's 1,238 lines" case). Docs
  never feed the map (code-is-truth); they only generate findings.
- Confidence surfacing: render the per-finding confidence count and the map's Disagreements
  prominently, so trust is visible (J3/J4).

**Risks / open:** matching a doc claim to the right part of the map; avoiding noise from intentionally
high-level docs.

*Re-plan this milestone before building it.*
