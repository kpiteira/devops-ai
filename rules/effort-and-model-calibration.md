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

A session states which model it is running on when it starts, and re-checks after any
restart: a session manager resumes on its default model after a tmux restart, and a child
session carries its parent's model. A planner session that finds itself on the executor
tier stops and says so rather than continuing — the pilot ran a replan on the wrong tier
twice before anyone read the status bar.

Effort and model selection are normally runtime/harness controls: a skill *recommends* a level
(as above) and the human or harness sets the session's. Treat the recommendations here as
defaults to reach for.

A skill can, however, pin its own execution for the turn it is active. The
[skill frontmatter reference](https://code.claude.com/docs/en/skills.md) documents `model:`
(a model id such as `claude-opus-5`, or `inherit` — "the same values as `/model`") and
`effort:` (`low`/`medium`/`high`/`xhigh`/`max`), both overriding the session for that turn
only; with `context: fork` the same `model:` sets the forked subagent's model instead, and
`agent:` picks the subagent type. That closes the open question this rule used to carry (see
`docs/designs/opus-4.8-evolution/INTENT.md`): pin a tier in frontmatter when the *skill*, not
the session, determines the right one, and otherwise leave it to the harness, because a
pinned tier is invisible in the status bar and outlives nobody's attention. `kbabysit` did
this (#45, `context: fork` + `model:`) and dropped it on 2026-09-14: a forked loop is
invisible in the session that runs it — a status line and nothing else, the rounds in a
sidechain transcript — so the babysit now runs in an Opus agent-deck session of its own
and its preflight states the model and stops on the wrong one. A pin that hides the work
it pins is the wrong pin.
