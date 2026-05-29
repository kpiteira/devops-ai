# Architect Skill Family

**Date:** 2026-05-15
**Status:** Intent — design conversation in progress
**Dogfood targets:** agent-memory (first), ktrdr (second)

---

## The Core Problem

The current pipeline (`/kdesign` → `/kplan` → `/kbuild`) produces codebases that drift architecturally. agent-memory is the worked example: 24K LOC, 23 top-level modules, six parallel `*Writer` classes, 420+ direct write sites bypassing the nominal gateway, ad-hoc LLM runtime preventing substitution between Claude Code and Copilot, dialogue logic intermixed with transport (Telegram/Teams) instead of a clean dialogue layer with medium-specific adapters. Karl was not vigilant about architecture and let Claude Code drive the structure feature-by-feature. The result is spaghetti.

The root causes:

1. **No conceptual model** — `/kdesign` mixes problem exploration with solution structure; architecture gets shortchanged because the conversational pull is toward "what should we build."
2. **No living map** — there is no maintained, queryable understanding of the existing codebase. Every new feature starts blind to surface area established by previous features.
3. **No adversarial review** — the same agent that designs the work also implements it. Anchoring bias means it cannot catch its own structural mistakes.
4. **No mechanical enforcement** — `/kbuild`'s quality gates are file-local (ruff, mypy, pytest). They cannot see cross-file duplication, layering violations, or architectural drift.

Diagnosing the May 2026 audit of agent-memory (which Karl found "meh"): it produced 23-dimension evidence coverage but no conceptual model. It went evidence → proposal without ever passing through "what are the real capabilities, what are the real seams, what is this system trying to be." The diagrams are shallow because they're filesystem-with-arrows, not conceptual models. **The missing step is synthesis.**

---

## The Goal

Three outcomes the architect skill family must enable:

1. **Audit** — factual discovery of structural problems in existing codebases (the kind of problems Karl knows exist in agent-memory: duplication, weak factorization, missing abstractions, layering drift).
2. **Correct** — capture the corrected architecture as living truth, drive refactor execution through `/kbuild`.
3. **Prevent** — design-time and implementation-time discipline that stops new features from regressing the architecture.

When the family is done well, a senior engineer joining the project gets a usable mental model from the first page of `ARCHITECTURE.md`, can answer "why is it like this?" by following links to ADRs, and can trust that new features will respect the canonical patterns rather than reinvent them.

---

## The Approach — Four Skills

Two orthogonal axes separate the work. Each skill has a distinct posture and temporal scope; folding any two into one reproduces the cognitive-mode-mixing problem the family is trying to solve.

| Skill | Posture | Temporal scope | Trigger |
|---|---|---|---|
| `karchitect-audit` | Forensic — find what's wrong | As-is | On demand · before major refactors · once on adoption |
| `karchitect-map` | Constructive — synthesize living truth | As-is | Post-merge · scheduled · after audit findings resolved |
| `karchitect-design` | Constructive — propose new structure | To-be | After `/kdesign`, before `/kplan` |
| `karchitect-review` | Adversarial — challenge claims | Delta | Gate 1 post-design · Gate 2 post-implementation |

`karchitect-audit` and `karchitect-map` share a **conceptual modeling phase** (the missing step). Audit uses modeling to make sense of the as-is. Map uses modeling to maintain canonical truth. Design extends the model for new work. Review challenges whether the model is honest.

---

## Grounding (recognized practice, not invented)

- **C4 Model (Simon Brown)** — Context / Container / Component / Code. Stable abstractions, zoom levels, "map zoom" metaphor. Most systems need only L1 + L2; L3 selectively; L4 almost never. The architect skills draw at C4 levels, not at filesystem level.
- **ADR (Michael Nygard format)** — Short text files, append-only, one decision per file. Diagrams show *what*; ADRs show *why*. Non-negotiable. ThoughtWorks Radar lists Lightweight ADRs as Adopt.
- **arc42 as checklist, not template** — Use arc42's section list to ask "did we forget quality requirements, constraints, risks?" Do not fill its 12 sections by default; that path leads to bureaucratic bloat.
- **Google design-doc shape** for narrative architecture documents: Context · Goals · Non-goals · Design · Alternatives · Cross-cutting. Bounded 5–15 pages. Inverted-pyramid prose.
- **Hohpe's architect elevator** — same architecture must be renderable at exec / onboarding / team-deep-dive altitudes. Multi-altitude is a first-class capability.
- **Will Larson's "write five, then synthesize"** — for brownfield audit, read five real flows in depth and derive the conceptual model from their commonalities, rather than starting top-down from "what should the architecture be."
- **Progressive disclosure + inverted pyramid** — the reading principle Karl named as "pyramidal communication." Standard term in the literature.

---

## The Audit Skill in Detail

`karchitect-audit` is a multi-agent skill that orchestrates parallel subagents with adversarial debate at synthesis points. It is significantly heavier than the other three skills. Built progressively in five layers, each producing a standalone deliverable:

| Layer | Output | Altitude |
|---|---|---|
| **L1** | System Context — one page, C4 L1 diagram, 4–7 conceptual components, key decisions, surprises | Top of pyramid |
| **L2** | Containers + critical flows — C4 L2 diagram, 1–3 sequence diagrams | One zoom level deeper |
| **L3** | Selective component depth — C4 L3 only where complexity demands it | Targeted deep dive |
| **L4** | Dimensional audit findings — A1–D7 catalog with severity, layered over L1–L3 | Cross-cutting evidence |
| **L5** | Synthesis & roadmap — composed multi-altitude document, sequenced milestones | Deliverable |

Build incrementally: L1 must pass validation against agent-memory before L2 begins. Each layer is a real deliverable for a reader; "internal substrate" layers are forbidden — they produce infrastructure with no validation surface.

**Parallelism and debate patterns** used inside the skill:

- **Independent re-derivation** for conceptual modeling: three modelers work blind, a synthesizer reconciles by demanding evidence for each claimed seam.
- **Pre-committed adversarial roles** for high-stakes calls (severity, PARALLEL claims): one agent argues "this is a real problem," another argues "this is acceptable variance," a judge decides on evidence.
- **Rejection lockout**: if a modeler's output is rejected at synthesis, a different agent revises. No one defends their own blind spot.

---

## Dogfood Plan

- **agent-memory** (24K LOC, Python) — primary dogfood target for L1 and L2. Has a recent human-led audit (May 2026) to compare against, plus Karl's intimate knowledge of its known problems.
- **ktrdr** (larger Python codebase) — secondary target for L3+ to test breadth and scaling.
- The architect skill family must be capable of designing itself (dogfood test). If it isn't, that's the highest-priority signal.

---

## Out of Scope

- This is not a rewrite of the existing pipeline. `/kdesign`, `/kplan`, `/kbuild`, `/kissue`, `/kreview`, `/kworktree`, `/kinfra-onboard` all remain. Some get narrower scope; none are removed.
- This is not a multi-agent orchestration framework. The skills are invoked by the user (or by other skills), not by an autonomous orchestrator. Sequential, human-in-the-loop, deliberate.
- This is not a polyglot tool. Initial implementation targets Python (where both dogfood projects live). The principle layer (C4, ADRs, dimension taxonomy, modeling method) is language-agnostic; deterministic tooling (radon, import-linter, jscpd) is language-specific. Extension to other languages is later work.
- This does not replace human architectural judgment. The skills systematize discipline; they do not produce trustworthy architecture from bad inputs.

---

## Open Questions

To be resolved as design progresses; not blockers for L1.

1. **Source format vs. reading format.** Markdown source vs. AsciiDoc vs. HTML; rendered output via MkDocs Material vs. Docusaurus vs. plain HTML. Deferred until artifacts are stable.
2. **Diagram source.** Mermaid is sufficient at L1; Structurizr DSL or D2 likely needed at L2+. Decide when L2 starts.
3. **Where ARCHITECTURE_INDEX lives** — single file vs. split per-package. Decide when `karchitect-map` is designed.
4. **Reviewer authority** — adversarial review produces findings only (current intent) or can patch artifacts directly. Current lean: findings-only; forces clean loop back through designer.
5. **Refresh staleness criteria** — when does the map require re-derivation? Probably hash-of-codebase-state vs. recorded-state, not a time threshold.

---

## Success Criteria for the Family

1. Running `karchitect-audit` on agent-memory produces an L1 System Context that Karl reads in 5 minutes and recognizes the known problems (memory-write proliferation, ad-hoc LLM runtime, dialogue-transport coupling) as surfaced surprises.
2. Subsequent layers (L2–L5) deepen without re-deriving the L1 view.
3. `karchitect-map` produces a living ARCHITECTURE.md that survives a feature's worth of `karchitect-design` + `/kplan` + `/kbuild` work without drift.
4. `karchitect-review` Gate 1 catches at least one structural problem in a real feature's design before implementation begins. Gate 2 catches at least one implementation drift.
5. The architect family has been used to design itself, and the resulting documents pass review.
