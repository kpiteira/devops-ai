---
design: docs/designs/karchitect-v2/DESIGN.md
architecture: docs/designs/karchitect-v2/ARCHITECTURE.md
---

# M1 — Core bottom-up loop (top level)

**Goal:** classify → break down every source file → cluster → N blind synthesizers → reconcile →
a high-level map + cross-cutting findings, run on agent-memory and validated against the v1 baseline.
**Stories:** J1 (high-level slice), J2, J3, J4, J7 (structured `map.json`), J8. **Exercises:** J6 (scale).

**Make-or-break:** this milestone tests the central bet — that synthesizing from *compressed
breakdowns* (not raw code) still surfaces cross-cutting problems like scattered access. If the gates
fail, reconsider the approach before planning M2.

## Negative space, invariants & interactions (M1)

No prior milestones, so no cross-feature interactions yet. What M1 must still get right:

- **Must reject / handle, not crash:** a path that doesn't exist; an empty repo (no source); a
  non-Python repo (empty source set); a binary or syntax-broken or very large file; a file an agent
  fails to break down (→ recorded as a coverage gap and re-dispatched, never silently dropped).
- **Invariants (enforced in the tested harness):** *partition* — every source file in exactly one
  batch, none dropped or doubled; *single membership* — every file in exactly one component;
  *coverage* — every inventory file appears in a breakdown/component or is set-aside-with-reason
  (hard-fail otherwise — this is J8).

---

## Task 1.1 — Data models

**File(s):** `src/devops_ai/audit/__init__.py`, `src/devops_ai/audit/models.py`, `tests/unit/test_audit_models.py`
**Type:** CODING
**Estimated time:** 2h

**Description:** Define the typed shapes everything else is built on (the design's pinned shapes):
`Edge` (kind: `import|call|reads_state|writes_state`, target, site), `FileBreakdown` (path,
classification, responsibility, edges, problems), `Component` (name, kind: `feature|shared`,
member_files, responsibility, depends_on), `Finding` (id, title, category, problem, consequence,
evidence_sites, confidence, severity, status), `HighLevelMap` (purpose, environment, components,
relationships, disagreements). JSON serialization both ways (for `map.json` and for passing
structured data to/from subagents).

**Implementation Notes:** Follow the `@dataclass` style in `src/devops_ai/ports.py`. Use enums (or
`Literal`) for the closed sets (Edge.kind, Component.kind, severity, status, classification).
Serialization can be `dataclasses.asdict` + a `from_dict` classmethod.

**Testing Requirements:**
- [ ] Round-trip: model → dict → model is identity for each type.
- [ ] **Rejects bad input:** an Edge missing `site`, a Component with empty `member_files`, an
      unknown enum value → validation error, not silent acceptance.
- [ ] `map.json` shape matches `HighLevelMap` (a fixture round-trips).

**Acceptance Criteria:**
- [ ] All five shapes exist, typed, with bidirectional JSON; tests pass.

---

## Task 1.2 — Inventory: walk, classify, partition

**File(s):** `src/devops_ai/audit/inventory.py`, `tests/unit/test_audit_inventory.py`
**Type:** CODING
**Estimated time:** 3h

**Description:** Walk a target repo (respect `.gitignore`), classify every file
(`source|test|doc|config|generated`), and partition the **source** files into N deterministic
batches for the breakdown fan-out. For M1 the load-bearing split is source-vs-rest; the richer
per-class handling is M2, but every file is still classified and recorded now (J8).

**Implementation Notes:** Pure functions over a path, returning a `FileInventory` dataclass
(`ports.py` style). Classify by extension + path heuristics (`.py`→source, `test_*.py`/`/tests/`
→test, `.md`→doc, `pyproject.toml`/`Dockerfile`/`.yml`→config, `vendor/`/generated markers
→generated). Partition = stable hash or sorted round-robin so it's reproducible.

**Testing Requirements:**
- [ ] Classification: each bucket hits its cases; `.gitignore`d files excluded.
- [ ] **Partition invariant:** union of batches == all source files, no duplicates, no drops.
- [ ] **Rejects/handles:** non-existent path (clear error); empty repo (empty source, no crash);
      non-Python repo (empty source set, handled); a binary/undecodable file (classified, not
      crashed on).

**Acceptance Criteria:**
- [ ] `FileInventory` lists every file with a classification; source partition satisfies the invariant.

---

## Task 1.3 — Breakdown stage (prompt + dispatch)

**File(s):** `skills/karchitect-audit/prompts/breakdown.md`, `src/devops_ai/audit/breakdown.py`, `tests/unit/test_audit_breakdown.py`
**Type:** MIXED
**Estimated time:** 4h

**Description:** A subagent reads each source file in a batch and emits a `FileBreakdown` —
one-line responsibility + **structured edges** (imports/calls/reads_state/writes_state, each with a
`file:line`) + any local problems. The dispatch (`breakdown.py`) runs one subagent per batch
(native fan-out) and collects all FileBreakdowns. The prompt is the cognition; the dispatch + output
validation is the code.

**Implementation Notes:** The prompt must push for *structured edges*, not prose — this is the
substrate cross-cutting findings are detected from (decision 1). `breakdown.py` validates each
returned record parses as a `FileBreakdown` and that the batch's files are all covered.

**Testing Requirements:**
- [ ] Output validation: a returned breakdown parses to `FileBreakdown` with well-formed edges
      (the parsing/validation code is unit-tested with fixture JSON).
- [ ] **Coverage within a batch:** every file in the batch has a breakdown, or is recorded as a
      gap — a missing file is not silently dropped.
- [ ] **Handles agent failure:** a garbage/empty agent return for a file → recorded as a gap and
      re-dispatched, asserted by a fixture that simulates a bad return.

**Acceptance Criteria:**
- [ ] Running breakdown over a sample of agent-memory source yields valid FileBreakdowns whose edges
      include real `writes_state`/`call` edges (e.g. on `services.py`).

---

## Task 1.4 — Clusterer

**File(s):** `src/devops_ai/audit/cluster.py`, `skills/karchitect-audit/prompts/cluster-name.md`, `tests/unit/test_audit_cluster.py`
**Type:** MIXED
**Estimated time:** 3h

**Description:** Build the dependency graph from `FileBreakdown.edges`, group files into components
(cohesion clusters), then a subagent names each component, assigns its kind (`feature|shared`), and
writes its one-line responsibility. Single membership enforced.

**Implementation Notes:** The graph + clustering is code (testable); naming/kind is the agent. A
high fan-in file → candidate `shared`. A file with heavy edges into two *feature* clusters → emit a
**coupling finding** rather than forcing a clean home.

**Testing Requirements:**
- [ ] **Single-membership invariant:** every file in exactly one component.
- [ ] A high-fan-in shared file is grouped/flagged as `shared`, not scattered.
- [ ] A straddling file produces a coupling-finding candidate (fixture graph).

**Acceptance Criteria:**
- [ ] On agent-memory, components are recognizable (not filesystem folders); shared infra is tagged `shared`.

---

## Task 1.5 — Synthesis stage (N blind synthesizers)

**File(s):** `skills/karchitect-audit/prompts/synth.md`, `src/devops_ai/audit/synth.py`, `tests/unit/test_audit_synth.py`
**Type:** MIXED
**Estimated time:** 4h

**Description:** M independent subagents (blind to each other) each build a `HighLevelMap` from the
breakdowns + components, and each surfaces cross-cutting findings detected over the aggregate edge
graph (e.g. "writes_state in 40 files → scattered access"). Dispatch collects M candidate maps +
M finding sets.

**Implementation Notes:** Synthesizers see *breakdowns* (the compression layer), not raw code —
this is the scale bet. The cross-cutting detection leans on the structured edges from 1.3.

**Testing Requirements:**
- [ ] Output validation: each synthesizer return parses to `HighLevelMap` (unit-tested with fixtures).
- [ ] Dispatch runs M independent agents and collects M results (no cross-contamination).

**Acceptance Criteria:**
- [ ] On agent-memory, synthesizers produce a high-level map, and cross-cutting findings include the
      scattered-access pattern derived from `writes_state` edges across many files.

---

## Task 1.6 — Reconciler

**File(s):** `src/devops_ai/audit/reconcile.py`, `skills/karchitect-audit/prompts/reconcile.md`, `tests/unit/test_audit_reconcile.py`
**Type:** MIXED
**Estimated time:** 4h

**Description:** Merge the M maps — agreement → high confidence; divergence → a **Disagreements**
section. De-duplicate findings (key = **category + overlapping evidence_sites**), score confidence
(how many synthesizers flagged it) and draft severity (blast-radius × risk).

**Implementation Notes:** The dedup + confidence scoring is code (testable); the map merge /
disagreement judgment is the agent. Severity is `high|med|low`, draft, Karl ratifies.

**Testing Requirements:**
- [ ] **Dedup:** two findings, same category + overlapping sites → merged, `confidence = 2/M`;
      different category or disjoint sites → kept separate.
- [ ] **Honest-uncertainty invariant:** if all M maps agree perfectly (Disagreements empty), that is
      flagged as a warning, not reported as success (gate 4).

**Acceptance Criteria:**
- [ ] On agent-memory, the merged map carries a non-empty Disagreements section, and findings carry a
      confidence count.

---

## Task 1.7 — Coverage check + artifact assembly

**File(s):** `src/devops_ai/audit/coverage.py`, `src/devops_ai/audit/assemble.py`, `tests/unit/test_audit_coverage.py`, `tests/unit/test_audit_assemble.py`
**Type:** CODING
**Estimated time:** 3h

**Description:** Coverage checker cross-checks final artifacts against the inventory: every source
file must appear in a breakdown/component, or be set-aside-with-reason — **hard-fail on any gap**
(this is the J8 guarantee). Assembler writes `MAP.md` (high-level for M1), `FINDINGS.md`,
`COVERAGE.md`, and `map.json` into `docs/architecture/audit/<ISO-timestamp>/` in the **target** repo.

**Implementation Notes:** Pure functions; `assemble.py` renders structured models to markdown +
json. `MAP.md` is high-level only for M1 (no drill-down — that's M2).

**Testing Requirements:**
- [ ] **Coverage hard-fails** when an inventory source file is absent from all breakdowns/components.
- [ ] A file set-aside-with-reason passes coverage; one set aside *without* a reason fails.
- [ ] `map.json` round-trips to `HighLevelMap`; `MAP.md`/`FINDINGS.md` render the expected sections.

**Acceptance Criteria:**
- [ ] Four artifacts written to the timestamped dir; coverage check enforces J8.

---

## Task 1.8 — SKILL.md orchestration

**File(s):** `skills/karchitect-audit/SKILL.md` (rewrite for v2 M1)
**Type:** MIXED
**Estimated time:** 3h

**Description:** The `/karchitect-audit` skill that wires the pipeline: run the harness
(inventory→partition), dispatch the breakdown fan-out (native subagents), cluster, dispatch the
synthesis fan-out, reconcile, run the coverage check, assemble artifacts. States *intent + the five
gates as contracts* and lets the harness do the deterministic parts and subagents the cognition.

**Implementation Notes:** De-restricted style — goal + contracts, not a scripted protocol (the v1
"rejection lockout / exact synthesis steps" is exactly what we're dropping). v1 SKILL.md is at
`1fdc2c9` for reference, not to copy. Invocation: `/karchitect-audit target: <path>` (M1 = layer 1).

**Testing Requirements:** None (skill prose); validated by Task 1.9.

**Acceptance Criteria:**
- [ ] The skill runs the full M1 pipeline end-to-end and names the five gates it must pass.

---

## Task 1.9 — VALIDATION: run on agent-memory

**File(s):** evidence captured under `docs/designs/karchitect-v2/implementation/` (validation notes)
**Type:** VALIDATION
**Estimated time:** 3h

**Description:** Run `/karchitect-audit` (M1 scope) on **agent-memory**. This is a **direct run with
observable artifacts** — not a sandbox/ke2e run (the audit has no running service). Validate:

- **Against the v1 baseline (`1fdc2c9` `FINDINGS.md`):** does M1 recover the known problems —
  F001 (`services.py` god-module), F002 (scheduler routing/approval), and the scattered-access
  pattern?
- **The five gates:** (1) Karl-readable in ~5 min; (2) altitude — no implementation detail in the
  high-level map; (3) reproducibility — two runs on the same SHA, components overlap >80%;
  (4) honest-uncertainty — Disagreements non-empty; (5) coverage-completeness — every source file in
  `COVERAGE.md`.
- **JTBD coverage audit:** J2 (findings present + `file:line` evidence) · J3 (confidence counts
  shown) · J4 (Disagreements present) · J8 (coverage check passed) · J1 (map readable).

**Human action:** Karl reads the high-level map cold and judges gate 1 (the 5-minute test). This is
the one step that cannot be automated — it's the point of the map.

**Acceptance Criteria:**
- [ ] All five gates pass; the v1-known findings are recovered; evidence (the artifacts + a
      comparison table vs v1) is recorded. A gate failure is a real result — it informs whether the
      bottom-up bet holds before M2 is planned.
</content>
