# Skills Modernization: Design

**Date:** 2026-02-13
**Status:** Draft

---

## Problem Statement

Our skills (~4,200 lines / ~65,000 tokens across 10 files) were built for Sonnet 4.5, which needed step-by-step recipes, rigid templates, and aggressive enforcement language. Opus 4.6 reasons from principles. The over-specification now degrades performance: prescribed pauses interrupt natural flow, templates constrain adaptive output, and aggressive language ("CRITICAL", "MANDATORY", "NEVER") causes overtriggering.

Additionally, ~18,000 tokens of identical config-loading boilerplate is copy-pasted across 9 skills, and three E2E testing agents are referenced everywhere but never defined.

## Goals

1. **Reduce token budget by ~70%** (65K → ~20K) by eliminating duplication and over-specification
2. **Shift from recipes to briefs** — communicate intent, principles, and constraints; let Opus decide how
3. **Extract shared patterns** to auto-loading rules so they're always available without duplication
4. **Enforce real E2E testing** structurally, not through agent ceremony
5. **Clean up dead references** (undefined agents, old SDD-era agents)

## Non-Goals

- Changing what the skills *do* — the workflow (design → plan → build → review) stays the same
- Adding new capabilities (agent teams, hooks) — separate designs
- Modifying kinfra CLI or kinfra-onboard behavior
- Per-project skill customization (global skills, project overrides via `.claude/skills/` if needed)

---

## Key Decisions

### D1: Merge kdesign + kdesign-validate into `/kdesign`

**Choice:** Single skill handles design exploration, architecture drafting, scenario validation, gap resolution, and milestone structure proposal.

**Rationale:** The boundary between "design" and "validate" was artificial for Sonnet. Opus naturally stress-tests designs during drafting. A separate validation session loses the design context and forces re-reading. The merged skill owns "what and why" — producing DESIGN.md, ARCHITECTURE.md, and a milestone structure.

**What survives from kdesign-validate:** Scenario tracing, gap analysis, and interface contracts — as principles, not prescribed steps. The conversation patterns ("what keeps you up at night?", "what's the constraint?") are genuinely valuable and stay.

### D2: Slim kdesign-impl-plan into `/kplan`

**Choice:** Keep as separate skill (different output type: implementation tasks) but reduce from 993 to ~250 lines. The task-type-categories appendix moves to a reference file.

**Rationale:** Implementation planning produces a different artifact (milestone files with tasks) and benefits from focused attention. The architecture alignment check (Step 0) is genuinely valuable and stays as a principle. The prescriptive Steps 1-6 with mandatory pauses become guidance.

**Input change:** `/kplan` receives milestone structure from `/kdesign` output and expands into tasks. Previously, milestone structure came from the separate kdesign-validate step.

### D3: Merge ktask + kmilestone into `/kbuild`

**Choice:** Single conversation handles both single-task execution and milestone orchestration. Opus manages context internally.

**Alternatives considered:** Keeping the subagent boundary (orchestrator spawns per-task subagents for context isolation). Rejected because Opus excels at long-horizon reasoning and can compact context when needed.

**What the merged skill does:**
- Given a single task: runs TDD cycle (research → RED → GREEN → REFACTOR → verify → handoff)
- Given a milestone: sequences tasks with quality verification between them, produces milestone completion report
- Manages context window itself — compacts when needed rather than forcing subagent boundaries

### D4: Extract shared patterns to `.claude/rules/`

**Choice:** Six rules files that auto-load for all conversations.

| Rule | Replaces | Purpose |
|------|----------|---------|
| `project-config.md` | ~50-line block in 9 skills | Config loading from `.devops-ai/project.md` |
| `tdd.md` | Duplicate sections in ktask, kissue | RED → GREEN → REFACTOR cycle |
| `quality-gates.md` | Duplicate sections in ktask, kmilestone | Tests pass, quality passes, committed |
| `handoffs.md` | Duplicate sections in ktask, kmilestone | Handoff document conventions |
| `vertical-slicing.md` | Sections in kdesign-validate, kdesign-impl-plan | Vertical milestone principles |
| `e2e-testing.md` | shared/e2e-prompt.md + references in 4 skills | Real E2E testing definition and enforcement |

**Rationale:** Rules auto-load for every file interaction. No duplication. Skills become thin wrappers that reference principles already in context.

### D5: E2E testing via rule + structural enforcement + test catalog

**Choice:** No separate E2E agents. Enforcement through:
1. A rule defining what "real E2E" means (always loaded)
2. Structural requirement: every milestone ends with a VALIDATION task
3. Evidence requirement: milestone completion reports must show what was tested against running infrastructure
4. Per-project test catalog for reuse

**Alternatives considered:** Three-agent ceremony (designer/architect/tester). Rejected because:
- The designer's job (find existing tests) is a catalog directory lookup
- The architect's job (design new tests) is inline work during /kbuild
- The tester's job (execute tests) is part of the VALIDATION task
- The ceremony was a Sonnet workaround — Opus can hold test design + execution in one context
- Opus can spawn subagents via the Task tool on its own when it judges context is tight

### D6: Language shift — principled, not prescriptive

**Choice:** Replace step-by-step recipes with intent + principles + constraints. No prescribed pauses, output templates, or step numbers.

**Example (before → after):**

Before:
```
## Step 1: Scenario Enumeration
Claude reads the design and architecture docs, then proposes 8-12 scenarios...
### Output format:
[full markdown template]
### Pause: Scenario Review
Claude asks: "These are my proposed scenarios..."
```

After:
```
## Validation
Validate the design through concrete scenario traces. Cover happy paths,
error paths, edge cases, and integration boundaries. Surface gaps as
decisions to make, not problems to report. Pause when you need input.
```

**What stays structured:** Task specification format in /kplan (because /kbuild consumes it). Milestone completion report format in /kbuild (because it feeds PR creation). These are interface contracts, not ceremony.

### D7: Clean up old SDD-era agents

**Choice:** Remove old agents from `~/.claude/agents/` (architecture-specialist, bundler-specialist, coder-specialist, milestone-planning-specialist, project_structure_analysis, requirements-specialist, roadmap-specialist, task-blueprint-specialist, validator-specialist). These are from Aug 2025, unused, and could confuse Opus if discovered.

### D8: Skill location — global with project overrides

**Choice:** Skills stay in `devops-ai/skills/`, symlinked to `~/.claude/skills/`. Projects can add `.claude/skills/` for project-specific skills that supplement or override globals.

---

## Change Overview

### Skills After Modernization

| Skill | Before | After | Change |
|-------|--------|-------|--------|
| `/kdesign` | 474 + 608 = 1,082 lines (2 skills) | ~200 lines (1 skill) | Merge kdesign + kdesign-validate |
| `/kplan` | 993 lines | ~250 lines + reference file | Slim, rename |
| `/kbuild` | 467 + 404 = 871 lines (2 skills) | ~200 lines (1 skill) | Merge ktask + kmilestone |
| `/kreview` | 283 lines | ~150 lines | Trim config boilerplate |
| `/kissue` | 267 lines | ~120 lines | Trim config + TDD (now in rules) |
| `/kworktree` | 174 lines | ~175 lines | Unchanged |
| `/kinfra-onboard` | 373 lines | ~300 lines | Light trim |
| `shared/e2e-prompt.md` | 155 lines | Removed | Absorbed into e2e-testing rule |

### New Components

| Component | Type | Estimated Size |
|-----------|------|----------------|
| 6 rules files | `.claude/rules/*.md` | ~1,500 tokens total |
| Test catalog convention | `docs/e2e-tests/` per project | Directory structure only |

### Removed Components

| Component | Reason |
|-----------|--------|
| `kdesign-validate` skill | Merged into `/kdesign` |
| `ktask` skill | Merged into `/kbuild` |
| `kmilestone` skill | Merged into `/kbuild` |
| `kdesign-impl-plan` skill | Renamed to `/kplan` |
| `shared/e2e-prompt.md` | Absorbed into rule |
| 9x old SDD agents | Unused, from Aug 2025 |

---

## Projected Token Budget

| Component | Before | After | Savings |
|-----------|--------|-------|---------|
| Design pipeline (kdesign + kdesign-validate + kdesign-impl-plan) | ~32,000 | ~7,000 | 78% |
| Execution pipeline (ktask + kmilestone) | ~13,500 | ~3,000 | 78% |
| Config boilerplate (9x repeat) | ~18,000 | ~1,500 (rules) | 92% |
| E2E prompt + agent references | ~2,400 | ~500 (rule) | 79% |
| Other skills (kreview, kissue, kworktree, kinfra-onboard) | ~17,000 | ~12,000 | 29% |
| **Total** | **~65,000** | **~20,000** | **69%** |

---

## E2E Testing Approach

### The Problem
Opus tends toward integration/smoke tests over real E2E tests. It takes the path of least resistance: "system starts without errors" passes but doesn't validate that the feature actually works.

### The Solution

**Layer 1: Definition (rule)**
`.claude/rules/e2e-testing.md` is always loaded. It defines:
- **Real E2E:** running infrastructure, real API calls, actual state changes, observable outcomes
- **Not E2E:** imports-without-errors, system-starts, mock-based assertions, component-level integration
- **When required:** every milestone completion

**Layer 2: Structure (task type)**
Every milestone in `/kplan` ends with a VALIDATION task. This is a structural requirement — not guidance that can be skipped. The task exists in the milestone file; /kbuild must execute it.

**Layer 3: Evidence (completion report)**
The milestone completion report in `/kbuild` must include:
- What capability was tested
- What commands were run against the running system
- What output was observed
- Pass/fail with evidence

Without this section, the milestone is not complete.

**Layer 4: Reuse (test catalog)**
Per-project test catalog at `docs/e2e-tests/` (or project's preferred location):
- Each test: purpose, prerequisites, steps, success criteria
- /kbuild checks catalog before designing new tests
- New tests are added to catalog after execution

---

## What Stays (Proven Valuable)

These principles emerged from real experience and survive in rules or skill briefs:

1. **TDD enforcement** (RED → GREEN → REFACTOR) → `.claude/rules/tdd.md`
2. **Handoff documents** → `.claude/rules/handoffs.md`
3. **Vertical slicing** (E2E-testable milestones) → `.claude/rules/vertical-slicing.md`
4. **kreview's critical assessment** ("don't blindly implement every suggestion") → stays in skill
5. **Architecture alignment check** → principle in `/kplan`
6. **Research before coding** → principle in `/kbuild`
7. **Conversation-first design** → principle in `/kdesign`
8. **Rosetta stone approach** (diagrams for humans, tables for LLMs) → principle in `/kdesign`
9. **Task specificity requirements** → principle in `/kplan`
10. **Real E2E over smoke tests** → `.claude/rules/e2e-testing.md`

---

## Open Questions (For Implementation)

1. Should the task-type-categories appendix from kdesign-impl-plan become a reference file in `.claude/` or stay inline in `/kplan`?
2. Exact test catalog directory structure — `docs/e2e-tests/` vs `.claude/e2e-tests/`?
3. Should rules use path-scoping (e.g., TDD rule only for `src/**/*.py`)? Probably not — these are universal principles.
