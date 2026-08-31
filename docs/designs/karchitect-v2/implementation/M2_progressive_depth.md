---
design: docs/designs/karchitect-v2/DESIGN.md
architecture: docs/designs/karchitect-v2/ARCHITECTURE.md
---

# M2 — Progressive depth + full classification  ·  SKETCH — re-plan before build

**Goal:** turn M1's high-level-only map into a *zoomable* one (high-level → components → file
breakdowns), and handle every file class properly (tests/docs/config/generated), not just source.

**Deepens:** J1 (progressive), J8 (complete classification).

**Key tasks (sketch):**
- Drill-down rendering in `assemble.py`: `MAP.md` links high-level → component → file breakdowns;
  `map.json` carries the nested levels.
- Full classification handling: tests mapped to *what they verify* (a coverage view + a finding
  source for untested critical components); config/build feeding the "how it's built/run" view;
  generated/vendored explicitly set aside in `COVERAGE.md`.
- Validation: zoom from top to any file on agent-memory; every file class accounted for.

**Risks / open:** how deep the auto-generated map should go before it's noise; whether drill-down is
always-materialized or rendered on demand.

*Re-plan this milestone (feeding M1's handoff) before building it.*
