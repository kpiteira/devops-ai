# karchitect audit — architecture

**Status:** design in progress · companion to `DESIGN.md`

## The pipeline (bottom-up)

```
   every file
      │
      ▼
┌─────────────┐   walk the tree, classify each file
│ 1. Classify │   → file inventory (source / test / doc / config / generated)
└─────┬───────┘
      │ source files (partitioned into batches)
      ▼
┌─────────────┐   fan-out: N agents, each breaks down its batch of files
│ 2. Break    │   every source file covered exactly once
│    down     │   → FileBreakdown records  + local findings
└─────┬───────┘
      │ all breakdowns (the "compression layer" — the whole system, low-res)
      ▼
┌─────────────┐   group breakdowns into components (cohesion / import graph)
│ 3. Cluster  │   → Component records
└─────┬───────┘
      │
      ▼
┌─────────────┐   M independent agents, blind to each other, each build the
│ 4. Synth    │   high-level map FROM the breakdowns+clusters
│  (×M blind) │   → M candidate maps  + cross-cutting findings
└─────┬───────┘
      │
      ▼
┌─────────────┐   merge the M maps: agree → high confidence; differ → record in
│ 5. Reconcile│   a Disagreements section. De-dupe findings, score confidence +
│             │   severity. → MAP.md + FINDINGS.md + COVERAGE.md
└─────┬───────┘
      │
      ▼   (M3) compare docs to the code-derived map → drift findings
      ▼   (M4) refresh: re-run steps 2–5 only for files changed since last audit
```

The fan-out (steps 2 and 4) is run by the harness's native subagents, **not** scripted step-by-step
in prose. The skill specifies *what must be true* — every source file covered once; synthesizers
work independently; the validation gates pass — and lets the model orchestrate. (This is the §3.2
"native orchestration" principle and the distillation's keep-#1/drop-#2 distinction.)

## Components

| # | Component | Responsibility | Output |
|---|-----------|----------------|--------|
| 1 | Classifier | Walk the tree; bucket every file by role | File inventory |
| 2 | Breakdown agents (fan-out) | Break down each source file once | FileBreakdown[] + local findings |
| 3 | Clusterer | Group breakdowns into components | Component[] |
| 4 | Synthesizers (×M, blind) | Build the high-level map from breakdowns | M candidate maps + cross-cutting findings |
| 5 | Reconciler | Merge maps (confidence + disagreements); de-dupe & score findings; **cross-check coverage against the inventory** (any file neither broken-down nor classified-and-set-aside is a hard gap → re-run); write artifacts | MAP.md, FINDINGS.md, COVERAGE.md |
| 6 | Drift checker *(M3)* | Compare docs to the map | Drift findings |
| 7 | Refresh controller *(M4)* | Diff git state; re-run 2–5 on changed files only | Updated artifacts |

## Data shapes (the atoms that calcify — pinned)

```
FileBreakdown:
  path:            str
  classification:  source | test | doc | config | generated
  responsibility:  str            # one line, what this file is for
  edges:           [Edge]         # STRUCTURED, not prose — the substrate cross-cutting
                                  #   findings are detected from (see Edge)
  problems:        [Finding]      # local problems noticed, with citation

Edge:                            # why structured: "writes scattered across 40 sites" and
  kind:  import | call | reads_state | writes_state   #  "Claude Code hardcoded vs abstracted"
  target:          str            #  are only detectable as patterns over the aggregate edge
  site:            file:line      #  graph — no single file "looks wrong" in isolation

Component:
  name:            str            # canonical, CamelCase noun (MemoryStore)
  kind:            feature | shared   # shared/foundational = legitimately cross-cutting
  member_files:    [path]         # SINGLE membership; identity = name + this set
  responsibility:  str
  depends_on:      [component-name]

Finding:
  id:              str            # F001…
  title:           str
  category:        str            # god-module | scattered-access | inconsistent-abstraction
                                  #   | coupling | drift | …  (half the dedup key)
  problem:         str            # stated as a problem, not a fact
  consequence:     str            # what it blocks or risks — the "so what"
  evidence_sites:  [file:line]    # one, or many for scattered findings
  confidence:      int / int      # synthesizers that flagged it. dedup key = category +
                                  #   overlapping evidence_sites
  severity:        high|med|low   # blast-radius × risk (draft; you ratify)
  status:          open | accepted | wont-fix

HighLevelMap:
  purpose:         str            # one paragraph, plain English
  environment:     [str]          # what the system touches (users, neighbours)
  components:      [Component]
  relationships:   [(from, to, what)]
  disagreements:   [str]          # where synthesizers differed — must be honest
```

## Artifacts (in the target repo)

Under `docs/architecture/audit/<ISO-timestamp>/`:

- **MAP.md** — the layered, human-readable map: purpose + environment + high-level components and how
  they connect, linking down to components → file breakdowns. Diagrams for humans (Mermaid/ASCII).
- **map.json** — the same, structured, for downstream skills (J7).
- **FINDINGS.md** — the findings catalog (the `Finding` shape above as a table).
- **COVERAGE.md** — every file, its classification, and analyzed-vs-set-aside, with reasons. This is
  the proof of J8 (no blind spots) and a J4 honesty artifact.

## Modes

- **Full** (first run): steps 1–5 over the whole codebase. Exhaustive, expensive, optimized for
  completeness.
- **Refresh** (stay green): the refresh controller diffs the working tree against the SHA recorded in
  the last audit and re-runs breakdown for the changed files **plus their blast radius** — the
  component each changed file belongs to, and any finding that cites it. (A local change can move a
  file between components or remove the write that anchored a cross-cutting finding, so refresh is
  *not* purely per-file.) Cheap, incremental, but scoped honestly.

## Scale (J6)

The breakdowns are a compression layer, so for mid-size repos (agent-memory ~24K LOC) the
synthesizers see all of them at once. For a repo large enough that even the breakdowns overflow one
synthesis context, fall back to **hierarchical synthesis**: synthesize per-package, then synthesize
across the package-level summaries. M1 on agent-memory tells us whether we need this yet; the data
shapes don't change either way (a package summary is just a higher-level map).

## Validation gates (carried from v1 — they were right)

A run isn't done until:

1. **Karl-readable** — you read the high-level map cold and in ~5 min can say what the system does and
   name its parts.
2. **Altitude discipline** — the high-level view has no implementation detail; components are concept
   nouns, not package names.
3. **Reproducibility** — two runs on the same SHA produce >80% overlapping components.
4. **Honest uncertainty** — the Disagreements section is non-empty (perfect agreement across blind
   synthesizers is a warning sign, not a success).
5. **Coverage completeness** *(new)* — COVERAGE.md accounts for every file; set-aside files have a
   stated reason.

## Integration points

- **Feeds "get clean":** FINDINGS.md is the input to a `/kdesign` refactor brief (clustering findings
  into themes happens there, not here).
- **Feeds the pipeline (J7):** map.json is machine-readable for downstream skills.
- **Boundary with quality gates:** lint-catchable problems (cross-file duplication, layering) are the
  always-on gates' job, not the audit's.
- **Boundary with "stay clean":** keeping MAP.md current as code changes is kbuild's Architecture
  Reconciliation; the audit's Refresh mode is for re-deriving it on demand, not per-commit.
</content>
