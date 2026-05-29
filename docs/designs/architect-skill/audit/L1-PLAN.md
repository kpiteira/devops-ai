# `karchitect-audit` — Layer 1 Plan: System Context

**Date:** 2026-05-15
**Status:** Plan — ready to build pending sign-off
**Prereq:** [INTENT.md](../INTENT.md) for family-level context

---

## Goal

Produce the **top of the pyramid**: a one-page artifact that gives a reader a usable mental model of a codebase in 5 minutes, and surfaces 3–5 honest "surprises" that signal where deeper audit layers should focus.

L1 has user-facing value on its own. It does *not* produce internal substrate or JSON facts files — those are infrastructure, used as needed by the LLM during the layer's work, but not deliverables.

---

## What L1 Produces

A single markdown artifact at:
`<target-project>/docs/architecture/audit/<ISO-timestamp>/01-system-context.md`

With these sections:

1. **What this system is** — one paragraph, plain English, no jargon.
2. **System Context Diagram** — C4 L1 (Mermaid), labelled boxes for the system, its users, and its neighbours. Diagram answers one named question, declared explicitly.
3. **Conceptual Components** — 4–7 components named by *what they conceptually do*, not by package name. One-line responsibility each, with a "roughly lives in" pointer to code.
4. **Key Architectural Decisions** — 3–5 draft ADR stubs (Title · Status · Context · Apparent Decision · Consequences). Includes *non-decisions* (patterns that emerged implicitly without an ADR).
5. **Surprises** — 3–5 honest observations where conceptual expectation diverges from code reality. This is where Karl's known pain should surface (e.g., "memory writes are scattered across 67 files with no single seam").
6. **Modeler Disagreements** — flagged uncertainty where independent modelers reached different conclusions.

---

## Process — Three Modelers + One Synthesizer

Four subagents total. The first three run in parallel.

### Modeler subagent (×3, parallel, blind to each other)

**Inputs:**
- README, top-level docs
- `pyproject.toml` (or equivalent package manifests)
- Top-level directory tree (depth ≤ 2)
- Entry points (CLI commands, `__main__.py`, public API modules)
- A sampling of 5–10 source files across distinct modules (not exhaustive — L1 is intentionally cheap)

**Output:** structured proposal containing all six sections above (minus disagreements), expressed as one modeler's view.

### Synthesizer subagent (×1, runs after all three modelers complete)

**Inputs:** all three modelers' proposals.

**Process:**
1. Identify where all three agree → goes into the artifact as high-confidence content.
2. Identify partial agreement (2 of 3) → goes in with a note.
3. Identify divergence (all three differ) → flagged in "Modeler Disagreements."
4. Compose the final `01-system-context.md`.

**Rejection lockout:** if the synthesizer judges any modeler's output as unsound, that modeler does not revise. A new modeler subagent is spawned and given the inputs fresh.

---

## Validation Gates

All four must pass before L2 work begins. Run on agent-memory.

1. **Karl-readable test.** Karl reads `01-system-context.md` cold. In ~5 minutes he can recite the system's purpose, name its conceptual components, and name 1–2 surprises. If he cannot, L1 is broken.

2. **Surprise-quality test.** At least 2 of the 3–5 surprises map to known agent-memory pain:
   - Memory-write proliferation (no single seam; 420+ direct writes)
   - LLM runtime ad-hoc (no abstraction enabling Claude Code/Copilot substitution)
   - Dialogue-transport coupling (dialogue logic intermixed with Telegram/Teams transport)
   - Six parallel `*Writer` classes
   
   If L1 surfaces none of these at the top altitude, the synthesizer prompt is iterated. The signal must reach the top of the pyramid.

3. **Reproducibility.** Run L1 twice on the same git SHA. Components and surprises overlap >80%. Exact phrasing varies; substance is stable.

4. **Honest uncertainty.** "Modeler Disagreements" section is non-empty. Three independent modelers agreeing perfectly is evidence of anchoring, not insight. The skill is designed to surface disagreement, not hide it.

---

## What L1 Must Refuse To Do

These belong to later layers and would cripple L1's altitude discipline if attempted:

- Catalogue dimension findings (A1–D7) → L4.
- Decompose components into sub-components → L2.
- Propose target architecture → `karchitect-design`'s job, downstream.
- Draw the package/folder structure and label it "architecture" → the most common failure mode.
- Produce more than one page of substantive content (excluding ADR stubs and diagram).

---

## Implementation Plan

Build in this order, no parallelism — each step gates the next.

### Step 1 — Skill skeleton

Create:
```
devops-ai/skills/karchitect-audit/
  SKILL.md                              # Phase 1 (L1) specified; L2-L5 marked TODO
  prompts/
    L1-modeler.md                       # Modeler subagent prompt
    L1-synthesizer.md                   # Synthesizer subagent prompt
  templates/
    01-system-context.md                # Output template the synthesizer fills
```

### Step 2 — Modeler prompt

Constraints embedded in the prompt:
- "You are one of three independent modelers. You will not see the others' work."
- "Sample 5–10 files across modules. Do not read everything. Time-box your reading."
- "Components must be conceptual, not package names."
- "Surprises must cite file paths."
- "At least one surprise must be about a missing abstraction, not just a present one."

### Step 3 — Synthesizer prompt

Constraints embedded:
- "Three modelers agreeing perfectly is a failure signal. Look for divergence."
- "Reject any modeler proposal whose components map 1:1 to top-level packages — that's filesystem-with-labels."
- "The diagram must answer a named question. If no question is named, ask one of the modelers (via re-run, not edit)."
- "Surprises must be honest. 'Everything looks fine' is not a surprise; it's a missed audit."

### Step 4 — Output template

The skeleton of `01-system-context.md` with section headers and one-line guidance under each. Synthesizer fills it.

### Step 5 — Dogfood run on agent-memory

Run the skill against `/Users/karl/Documents/dev/agent-memory`. Output goes to `agent-memory/docs/architecture/audit/<timestamp>/01-system-context.md`.

### Step 6 — Validation

Walk through the four gates with Karl. Iterate prompts (not architecture) until all four pass.

### Step 7 — Record learnings

Append a `HANDOFF.md` in this design folder capturing what worked, what the prompts had to enforce, and any open questions for L2.

---

## Cost Estimate

Per run on agent-memory-sized codebase:
- Three modelers × ~30–60K input tokens each, ~10–20K output → ~120–240K total input, ~30–60K output
- Synthesizer × ~50–100K input (modelers' outputs + spot-checks), ~5–10K output
- Estimated total: ~200–350K tokens per L1 invocation
- Wall time: ~5–10 minutes

Cost is dominated by the modelers' code sampling. Bounded by the "5–10 file sample" discipline; if a modeler reads exhaustively, prompts need re-tightening.

---

## Acceptance Criteria

L1 is complete when:

- [ ] `skills/karchitect-audit/` exists with SKILL.md, modeler prompt, synthesizer prompt, output template
- [ ] Skill runs end-to-end on agent-memory and produces `01-system-context.md`
- [ ] All four validation gates pass on agent-memory
- [ ] HANDOFF.md captures iterations made to the prompts during validation
- [ ] L2 plan can be drafted using L1's actual output as input (no re-derivation needed)

---

## Out of Scope for L1

Explicit deferrals to keep L1 honest:

- No deterministic tooling (no jscpd, import-linter, radon, Serena). L1 is pure LLM; introducing tools at this altitude confounds modeling quality with tool failure modes.
- No multi-language support. agent-memory is Python; ktrdr is Python. The principle layer is language-agnostic, but L1's prompts assume Python conventions for sampling.
- No `karchitect-map` integration. L1's output is a one-shot artifact. Conversion into a living index is `karchitect-map`'s problem, designed later.
- No Gate 1/Gate 2 review wiring. `karchitect-review`'s adversarial loop is designed separately.
