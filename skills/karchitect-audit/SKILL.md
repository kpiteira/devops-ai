---
name: karchitect-audit
description: Forensic architectural audit of a codebase. Produces a multi-altitude architectural understanding and a parallel findings catalog. Built in layers; only Layer 1 (System Context) is currently implemented.
metadata:
  version: "0.2.0"
---

# Architect Audit

Perform a forensic audit of an existing codebase. The skill produces two parallel output streams:

1. **Description stream** — progressively deeper *descriptions* of what the system is, at recognized C4 altitudes. L1 = System Context. L2 = Containers + critical flows. L3 = Selective component depth. Pure description; no analysis.
2. **Findings stream** — a single accumulating `FINDINGS.md` catalog of problems noticed during description, with evidence, draft severity, and (at L4) dimension tags. Findings can be appended at any layer.

These streams are deliberately separate. Mixing them is the failure mode that produces audits like agent-memory's May 2026 catalog — many findings without an honest conceptual model. Build the model first; let findings accumulate alongside it.

This skill is **multi-agent**: parallel subagents with synthesis. Each layer produces a real, reader-facing deliverable.

## Status

| Layer | Description-stream output | Implemented |
|---|---|---|
| **L1 — System Context** | One-page top-of-pyramid view: prose + environment diagram + conceptual structure diagram + component table | ✅ |
| **L2 — Containers & critical flows** | C4 L2 container view + 1–3 sequence diagrams for flows that earn the system its keep | TODO |
| **L3 — Selective component depth** | C4 L3 for components where complexity demands it | TODO |
| **L4 — Dimensional audit findings** | A1–D7 catalog with severity (refines the running `FINDINGS.md`) | TODO |
| **L5 — Synthesis & roadmap** | Composed multi-altitude document + sequenced refactor milestones | TODO |

Each layer must validate against its gates before the next runs.

## Outputs

In the target project under `docs/architecture/audit/<ISO-timestamp>/`:

- `01-system-context.md` — L1 description artifact
- `FINDINGS.md` — running catalog, started at L1, refined at every later layer

## Invocation

```
/karchitect-audit target: <path> layer: 1
```

Default `target` is the current repository. Default `layer` is the lowest unimplemented layer.

---

## Layer 1 — System Context

### What L1 produces

A **pure-description** artifact answering one question: *what does this system do?* Three views of the same answer:

1. **Prose** — one paragraph stating what the system does, in plain English a non-coder can follow.
2. **Environment diagram** (C4 L1 System Context) — the system as one box surrounded by its users and neighbours. *High altitude only*: every label is conceptual (e.g., "drives an LLM", "messages humans", "persists state"). No port numbers, API endpoints, file paths, protocol names, or implementation specifics.
3. **Conceptual structure diagram** — the system's internal *conceptual* components shown as boxes with relationships. Names are CamelCase nouns (`MemoryStore`, `DialogueEngine`) — not package names. This is the diagram a reader uses to form a mental model of *what the system is made of*.
4. **Conceptual components table** — paired with the structure diagram for reference lookup. Same components, with one-line responsibility and a pointer to roughly where each lives in code.

L1 also accumulates **findings to a separate file** (`FINDINGS.md`) — observations noticed while building the description. These do **not** appear in `01-system-context.md`.

### What L1 must refuse to do

- **No analysis in the description artifact.** No "this is a god object", no "missing abstraction" call-outs, no severity, no recommendations. Description only.
- **No implementation specifics in the environment diagram.** If a label would require knowing this codebase to understand, it's too low altitude.
- **No package names in the conceptual structure.** That's filesystem-with-labels.
- **No ADRs at L1.** Decision history requires context the higher layers don't have yet. Deferred.
- **No more than ~1 substantive page in the description artifact** (excluding diagrams and component table).

### Process

Four subagents in two phases.

**Phase 1: three modelers in parallel (blind to each other)**

Spawn three Agent subagents in a single message. Each receives:
- Target codebase path
- Modeler prompt at `prompts/L1-modeler.md`
- An instruction: "you are modeler N of 3; you will not see the other modelers' work"
- A modeler-specific findings-notes path (e.g., `<audit-tmp>/findings-modeler-N.md`) for side-channel observations

Each modeler reads README + manifests + top-level tree + entry points + a 5–10 file sample. Each independently produces:

- System purpose paragraph
- Environment diagram (Mermaid, high altitude)
- Conceptual structure diagram (Mermaid)
- Conceptual components table

And optionally appends findings (one per finding, with citation) to its findings-notes file.

**Phase 2: one synthesizer**

After all three modelers return, spawn the synthesizer Agent with:
- All three modeler proposals
- All three findings-notes files
- Synthesizer prompt at `prompts/L1-synthesizer.md`
- Output template at `templates/01-system-context.md`
- Output paths for the description artifact and the findings catalog

The synthesizer:
1. Reconciles modelers' descriptions: agreement (high confidence) / partial agreement (note dissent) / divergence (flag in disagreements).
2. Composes the L1 description artifact using the template — pure description only.
3. Reconciles findings: de-duplicates across modelers' notes, assigns each a draft ID and draft severity, writes them to `FINDINGS.md` with layer-of-origin tag (`L1`).
4. Writes both artifacts.

**Rejection lockout**: if the synthesizer judges a modeler's output unsound (e.g., environment diagram has implementation specifics, structure diagram is filesystem-with-labels, components are package names, output exceeds 1.5 pages, description contains analysis), spawn a fresh modeler subagent and re-run synthesis.

### Validation gates

All must pass before L2.

1. **Karl-readable** — present the description artifact to the user. They read it cold; in ~5 minutes they can state what the system does, point at the conceptual structure diagram and name its parts, and identify what the system touches in its environment.
2. **Altitude discipline** — environment diagram has zero implementation specifics; conceptual structure diagram has zero package names. If either fails, iterate the modeler prompt.
3. **Reproducibility** — run L1 twice on the same git SHA. Conceptual components and structure overlap >80%.
4. **Honest uncertainty** — Modeler Disagreements section in the description is non-empty. Three modelers agreeing perfectly is anchoring.

### Findings catalog format

`FINDINGS.md` is the parallel artifact, started at L1 and grown at every later layer.

```markdown
# Architecture Findings — <Project>

| ID | Layer | Title | Evidence | Draft severity | Status |
|---|---|---|---|---|---|
| F001 | L1 | <one-line> | `file:line` | High / Med / Low (draft) | open |
```

At L1 the severity field is "draft" — formal severity comes at L4 with the dimension audit. Status starts at `open`; future layers (or `karchitect-design` / `/kbuild`) may update to `addressed` or `wont-fix`.

Findings should be observations of *problems*, not facts. "MemoryService is 2,286 lines" is not a finding; "MemoryService has accreted unrelated responsibilities into a god object (`services.py`, 2,286 LOC, ~50 methods spanning pipeline phases, dialogue, migration, squad spawning)" is.

---

## L2–L5

TODO — designed after L1 passes validation on agent-memory.

## Tool dependencies

L1: none beyond standard LLM access (file reading, Agent tool for subagent spawning).
L2+: language-aware tooling list specified per layer.
