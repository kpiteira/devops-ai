# System Context — {ProjectName}

**Generated:** {ISO-timestamp}
**Git SHA:** {sha}
**Audit layer:** L1 (System Context — description)
**Modelers:** 3 independent + 1 synthesizer

> This is a **pure description** of what the system does. Findings (problems, missing abstractions, god objects, security concerns) live in `FINDINGS.md` alongside this file.

---

## What this system does

> One paragraph, plain English, no jargon, no implementation specifics. A non-coder should follow it.

---

## Environment Diagram

**Question this diagram answers:** {explicit question, e.g. "What does this system communicate with in its environment?"}

```mermaid
{C4Context or graph TB.
 - Every box: a role or external system, conceptually named.
 - Every arrow's verb: a capability, not a protocol.
 - No port numbers, file paths, SDK names, API routes, env vars.
}
```

---

## Conceptual Structure Diagram

**Question this diagram answers:** {explicit question, e.g. "What are this system's main internal parts and how do they relate?"}

```mermaid
{flowchart with CamelCase conceptual components.
 - Names are conceptual nouns, NOT package names.
 - Arrows describe conceptual relationships.
}
```

---

## Conceptual Components

| Component | Responsibility (one line) | Roughly lives in |
|---|---|---|
| `{CamelCaseName}` | {verb-first one-liner} | `{pkg}/`, `{file.py:func}` |

> 4–7 components. Conceptual names only. Paired with the Conceptual Structure Diagram above — same set of components.

---

## Modeler Disagreements

> Non-empty. Three modelers agreeing perfectly is anchoring, not insight.

- {disagreement 1 — what differed and why it matters}
- {disagreement 2}
- {single-modeler observations worth noting}

---

**Synthesis footer**

- Modelers: {3}
- Files touched (union across modelers): {N}
- Rejections during synthesis: {0 / list with reasons}
- Findings catalogued: {N — see `FINDINGS.md`}
- Synthesizer note: {one-line meta-observation, if any}
