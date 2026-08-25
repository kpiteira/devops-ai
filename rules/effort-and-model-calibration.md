# Effort and Model Calibration

Match the reasoning budget to the difficulty of the work. Spending maximum effort on a fixed-format
lookup wastes it; starving a hard design problem of effort produces shallow work. The goal is
*quality where it counts* — not uniform spend.

## Effort levels

`xhigh` is the right setting for the heavy reasoning work: planning, implementation,
architectural analysis (`/kspec`, `/kbuild`, and any audit/review skill). It is the
recommended level for most coding and agentic tasks on current Opus models. The v2
contract's model tiering (planner on the strongest frontier model, executor on the
strongest cost-effective coding model) is set per-session by the human or harness.

`high` (the default) fits the lighter, more linear skills where the path is mostly known and the
judgment is local: addressing review comments (`/kreview`), implementing a scoped issue
(`/kissue`).

Lower tiers fit narrow, well-specified subtasks — catalog lookups, mechanical scans,
fixed-format extraction — where the answer space is small and the work is closer to retrieval than
reasoning.

## Model tiering

When a skill orchestrates subagents, the orchestrator runs on the strong model and delegates
*scoped, well-specified* subtasks to cheaper tiers. `ke2e` is the proven pattern: scout (a catalog
lookup) on a small model, designer (open-ended test design) on the strong model, runner (execute
and report) in between. Tier down only where it doesn't degrade output — a cheaper model on a task
that needs real reasoning is a false economy, and we optimize for quality first.

## How this gets set

Effort and model selection are runtime/harness controls — a skill can *recommend* a level (as
above) but the human or harness sets it. Treat the recommendations here as defaults to reach for,
not as something a skill can enforce on its own. (Whether a skill can declare its effort in
frontmatter is an open question — see `docs/designs/opus-4.8-evolution/INTENT.md`.)
</content>
