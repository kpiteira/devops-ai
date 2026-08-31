---
design: docs/designs/karchitect-v2/DESIGN.md
architecture: docs/designs/karchitect-v2/ARCHITECTURE.md
---

# M4 — Refresh mode (stay green)  ·  SKETCH — re-plan before build

**Goal:** keep the map current without a full re-run — re-derive only what changed.

**Owns:** J5 (freshness).

**Key tasks (sketch):**
- Refresh controller: diff the working tree against the SHA recorded in the last audit; re-run
  breakdown for changed files **+ their blast radius** (the component each belongs to, and any
  finding citing them) — not purely per-file, because a local change can move a file between
  components or remove the write that anchored a cross-cutting finding.
- Incremental re-synthesis + re-reconcile over the affected subset; update artifacts in place.

**Risks / open:** correctly bounding the blast radius; deciding when a change is large enough that a
full re-run is cheaper than an incremental one.

*Re-plan this milestone before building it.*
