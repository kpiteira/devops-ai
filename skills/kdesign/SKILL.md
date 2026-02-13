---
name: kdesign
description: Design and validate features through collaborative exploration. Produces DESIGN.md, ARCHITECTURE.md, and a milestone structure.
---

# Design Command

Generate, validate, and refine design and architecture documents for a feature or system change. This replaces the separate design, validation, and milestone-structure steps with a single conversation.

## What This Produces

1. **DESIGN.md** — The what and why: problem statement, goals, non-goals, user scenarios, key decisions with trade-offs
2. **ARCHITECTURE.md** — The how: components, data flow, state, errors, interface signatures, integration points
3. **Milestone structure** — Vertical slices ready for implementation planning

## Command Usage

```
/kdesign feature: <description> [context: <relevant-docs>]
```

---

## This is a Conversation, Not a Generator

The value comes from the back-and-forth, not from the first draft. Claude proposes, you refine. Claude finds gaps, you make decisions.

- Claude will miss scenarios. You know what's flaky, what failed before, what "feels wrong."
- Claude will propose approaches. You know which constraints actually matter.
- Gaps are discoveries, not failures. Every gap found now saves hours later.

---

## What to Explore

### Problem Space

Before proposing solutions, understand the problem:
- What problem are we solving? Who experiences it?
- What does success look like?
- What constraints exist?

Share a problem statement (2-3 sentences). Get alignment before moving on.

### Solution Options

Explore 2-3 approaches with trade-offs. Not every feature needs multiple options — simple features can have an obvious best approach.

For each option: how it works, what it makes easy, what it makes hard, what the risks are. Share a recommendation with reasoning.

### Architecture

Design the system structure:
- Components and their responsibilities
- Data flow (how information moves through the system)
- State management (where state lives, lifecycle)
- Error handling (what can go wrong, what happens)
- Integration points (what existing code changes)

### Validation

Trace concrete scenarios through the architecture to find gaps:

**Scenario types to cover:**
- Happy paths (primary use case, key variations)
- Error paths (expected failures, recovery flows)
- Edge cases (cancellation, concurrent operations, ambiguous state transitions)
- Integration boundaries (cross-component communication, external systems)

**For each scenario**, trace step-by-step: which component handles it, what's the input, what processing occurs, what state changes, what could go wrong.

**Gap categories to look for:**
- State machine gaps — transitions not covered, ambiguous intermediate states
- Error handling gaps — failures without defined behavior
- Data shape gaps — undefined or ambiguous data structures
- Integration gaps — unclear component boundaries or ownership
- Concurrency gaps — race conditions, ordering issues

Gaps are decisions to make, not problems to report. For each gap: present options, trade-offs, and a recommendation. Record the decision.

### Milestones

Propose a vertical milestone structure. Each milestone should be E2E-testable, build on the previous one, and deliver user-visible value. The `vertical-slicing` rule has the core principles.

Milestone 1 is the smallest thing that proves the architecture works end-to-end — testable, not necessarily useful.

---

## Design Principles

**Right-sized:** Match documentation depth to complexity. A small change might not need formal docs. A large system might need docs split by component.

**Decisions over description:** Capture why, not just what. "Uses a queue because operations take 30+ seconds and we don't want to block the API" beats "uses a queue."

**Acknowledge uncertainty:** Open questions are fine. Name them rather than pretending certainty.

## Architecture Principles

**Rosetta stone:** Diagrams for humans (ASCII box-and-arrow), structured tables for LLM consumption. Both capture the same information.

**Interface signatures, not implementations:** Show method names, parameters, return types. If someone could copy-paste it as working code, it's too much detail.

**Right level of detail:** Enough to create implementation tasks, not so much that you've done the implementation.

---

## Conversation Patterns

These patterns produce the best results:

- **"What keeps you up at night?"** — After proposing scenarios, ask what feels risky even if hard to articulate. The answer often reveals scenarios Claude would never think of.
- **"What's the constraint?"** — When a gap has multiple options, ask for the real constraint. It often simplifies the decision.
- **"Does this remind you of anything?"** — Past failures predict future failures. When a gap surfaces, ask if it's familiar.
- **"Let me trace that"** — When the user adds a scenario, trace it immediately. The act of tracing often reveals surprises.
- **"What would you need to see to decide?"** — When the user is uncertain, ask what information would help.

---

## Output

Save to the configured design documents path (from project config):

```
docs/designs/<feature-name>/
  DESIGN.md
  ARCHITECTURE.md
```

The milestone structure can be included at the end of the design output or as a separate section — whatever fits the conversation.

### When Validation Reveals Rework

If validation finds many critical gaps (>5), the design likely needs another iteration. Say so. It's better to discover this now than after writing code.

### When Design Isn't Needed

Skip formal design docs when the change is small and obvious, you're spiking to learn something, or the implementation will be faster than the design.
