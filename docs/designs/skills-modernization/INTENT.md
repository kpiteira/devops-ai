# Skills Modernization for Opus 4.6

**Date:** 2026-02-13
**Status:** Intent — needs design discussion via `/kdesign`
**Context:** Skills were built with and for Sonnet 4.5. Now running Opus 4.6.

---

## The Core Problem

Our skills (~4,200 lines / ~65,000 tokens across 10 files) were designed to compensate for Sonnet 4.5's weaker reasoning by providing detailed step-by-step procedures, rigid templates, and aggressive enforcement language. Opus 4.6 reasons from principles, not recipes. The over-specification now *degrades* performance by constraining the model's natural reasoning.

Anthropic's official guidance for Opus 4.6:
- "Where you might have said 'CRITICAL: You MUST use this tool when...', you can use more normal prompting like 'Use this tool when...'"
- "If your prompts previously encouraged the model to be more thorough or use tools more aggressively, dial back that guidance"
- "Replace blanket defaults with more targeted instructions"
- "Remove over-prompting. Tools that undertriggered in previous models are likely to trigger appropriately now"

---

## Research Summary

### Anthropic Guidance Sources Consulted

1. [Claude 4 Best Practices](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
2. [What's New in Claude 4.6](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-6)
3. [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills)
4. [Claude Code Subagents Documentation](https://code.claude.com/docs/en/sub-agents)
5. [Claude Code Memory Documentation](https://code.claude.com/docs/en/memory)
6. [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams)
7. [Claude Agent SDK](https://claude.com/blog/building-agents-with-the-claude-agent-sdk)
8. [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
9. [Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)

### Key Opus 4.6 Characteristics Affecting Skill Design

- **Adaptive thinking**: Dynamically allocates reasoning depth based on complexity
- **Effort levels**: Low/Medium/High control reasoning depth
- **Precise instruction following**: Does exactly what you say (overtriggers on aggressive language)
- **Natural subagent orchestration**: Recognizes when to delegate without being told
- **Concise communication style**: More direct, less verbose than previous models
- **Overthinking tendency**: May over-explore at high effort settings
- **Overengineering tendency**: May add unnecessary abstractions
- **Parallel tool calling**: Excellent at running independent operations simultaneously
- **Long-horizon reasoning**: Excels at sustained multi-step autonomous work
- **Context awareness**: Tracks remaining context window

---

## Current Skill Inventory

| Skill | Lines | Tokens | Purpose |
|-------|-------|--------|---------|
| kdesign | 474 | ~7,500 | Design generation |
| kdesign-validate | 608 | ~9,500 | Design validation |
| kdesign-impl-plan | 993 | ~15,000 | Implementation planning |
| ktask | 467 | ~7,200 | Task implementation (TDD) |
| kmilestone | 404 | ~6,300 | Milestone orchestration |
| kreview | 284 | ~4,400 | PR review |
| kissue | 268 | ~4,100 | Issue implementation |
| kworktree | 175 | ~2,700 | Worktree management |
| kinfra-onboard | 374 | ~5,800 | Project onboarding |
| shared/e2e-prompt | 156 | ~2,400 | E2E testing workflow |
| **Total** | **4,203** | **~65,000** | |

### Identified Issues

1. **Config loading boilerplate**: Identical 50-line block copy-pasted into 9 of 10 skills (~18K wasted tokens)
2. **Three-stage design pipeline**: kdesign → kdesign-validate → kdesign-impl-plan = 3 sessions with context loss. The boundary between "design" and "validate" is artificial for Opus.
3. **Prescriptive procedures**: Step-by-step recipes with exact output templates. Opus performs better with intent + constraints.
4. **Undefined subagents**: e2e-test-designer/architect/tester referenced but never defined as `.claude/agents/`
5. **No hooks**: All quality gates manually enforced via skill text
6. **No `.claude/rules/`**: Shared principles embedded in individual skills instead of auto-loading rules
7. **Rigid sequential workflows**: Designed for Sonnet's recipe-following, not Opus's judgment
8. **Aggressive language**: "CRITICAL", "MANDATORY", "NEVER", "MUST" everywhere — causes overtriggering with Opus

---

## Proposed Changes

### Change 1: Extract Shared Patterns to `.claude/rules/`

Rules auto-load for all files. No duplication. Skills become thin wrappers.

```
.claude/rules/
  project-config.md    # Config loading from .devops-ai/project.md
  tdd.md               # TDD: RED -> GREEN -> REFACTOR
  quality-gates.md     # Tests pass, quality passes, committed
  handoffs.md          # Handoff document conventions
  vertical-slicing.md  # Vertical milestone principles
```

**Impact:** ~18K tokens of boilerplate eliminated. Shared principles always available.

### Change 2: Merge kdesign + kdesign-validate into `/kdesign`

Opus naturally stress-tests its own designs during drafting. The separate "validate" step was needed for Sonnet because it couldn't hold both modes. Opus does exploration + validation in one conversation.

**Before:** 474 + 608 = 1,082 lines
**After:** ~200 lines

The merged skill communicates intent and principles:
- Explore the problem space, draft design + architecture
- Validate through concrete scenario traces
- Surface gaps as decisions, resolve in conversation
- Produce DESIGN.md, ARCHITECTURE.md, SCENARIOS.md

No rigid step numbers, no template outputs, no prescribed pause points. Opus decides when to pause and what format to use.

### Change 3: Slim kdesign-impl-plan into `/kplan`

Keep separate (different output type) but reduce from 993 to ~250 lines. The 8-category task type appendix becomes a reference file, not inline content. Architecture alignment check stays (valuable) but as a principle, not a rigid Step 0.

**Before:** 993 lines
**After:** ~250 lines + optional reference file

### Change 4: Merge ktask + kmilestone into `/kbuild`

kmilestone is "invoke /ktask in a loop." Opus can handle both modes:
- Given a single task: run TDD cycle
- Given a milestone: sequence tasks with quality verification between them

**Before:** 467 + 404 = 871 lines
**After:** ~200 lines

### Change 5: Define Custom `.claude/agents/`

Create proper subagent definitions:

```
.claude/agents/
  e2e-test-designer/    # Haiku, read-only, catalog search
  e2e-test-architect/   # Opus, test design
  e2e-tester/           # Opus, test execution
  test-quality-checker/ # Haiku, fast quality check
```

Each with frontmatter: model, tools, permissions, description. Makes them real, discoverable, configurable.

### Change 6: Add Hooks for Quality Automation

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "command": "auto-format on source files"
    }],
    "TaskCompleted": [{
      "command": "verify handoff exists if task type requires it"
    }],
    "Stop": [{
      "command": "quality gate check"
    }]
  }
}
```

### Change 7: Shift Language from Prescriptive to Principled

**Before (Sonnet-era):**
```
## Step 1: Scenario Enumeration
Claude reads the design and architecture docs, then proposes 8-12 scenarios...
### Output format:
[full markdown template]
### Pause: Scenario Review
Claude asks: "These are my proposed scenarios..."
```

**After (Opus-era):**
```
## Approach
Validate the design through concrete scenario traces. Cover happy paths,
error paths, edge cases, and integration boundaries. Surface gaps as
decisions to make, not problems to report. This is a conversation — pause
when you need input, not at prescribed checkpoints.
```

Opus decides *when* to pause, *how many* scenarios, *what format*. The result adapts to the specific situation.

### Change 8: Leverage opusplan and Effort Levels

- `/kdesign`: model opus, high effort (architectural reasoning)
- `/kbuild`: medium effort for coding, high for validation
- `/kreview`: model sonnet or medium effort (straightforward assessment)
- `/kissue`: model sonnet or medium effort (straightforward TDD)

### Change 9: Light Trims on Other Skills

- **kreview**: Already well-designed. Trim config boilerplate (now in rules). ~150 lines.
- **kissue**: Trim config boilerplate, slim TDD section (now in rules). ~150 lines.
- **kworktree**: Unchanged (already concise reference).
- **kinfra-onboard**: Light trim, keep phased structure (appropriate for destructive operations). ~300 lines.

---

## Projected Token Budget

| Component | Before | After | Savings |
|-----------|--------|-------|---------|
| Design pipeline (3 skills) | ~32,000 | ~7,000 | 78% |
| Execution pipeline (2 skills) | ~13,500 | ~3,000 | 78% |
| Config boilerplate (9x repeat) | ~18,000 | ~1,500 (rules) | 92% |
| Other skills (kreview, kissue, etc) | ~7,000 | ~5,500 | 21% |
| Custom agents (new) | 0 | ~2,000 | — |
| Rules (new) | 0 | ~1,500 | — |
| **Total** | **~65,000** | **~17,000** | **74%** |

---

## What Stays the Same (Proven Valuable)

These emerged from real experience and should survive in rules or skill principles:

1. **TDD enforcement** (RED -> GREEN -> REFACTOR) — moves to `.claude/rules/tdd.md`
2. **Handoff documents** — moves to `.claude/rules/handoffs.md`
3. **Vertical slicing** — moves to `.claude/rules/vertical-slicing.md`
4. **kreview's critical assessment** — skill is well-designed already
5. **E2E testing distinction** (real vs shallow) — preserved in agent definitions
6. **Architecture alignment check** — integrated into `/kplan` as principle
7. **Research before coding** — preserved as principle, not rigid phase
8. **Conversation-first design** — preserved as principle, not prescribed pauses

---

## Future Capabilities to Explore

### Agent Teams (Experimental)

For large milestones, agent teams could parallelize:
- Lead agent orchestrates milestone
- Teammate 1 implements task N
- Teammate 2 writes tests for task N+1

Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. Worth prototyping.

### Skill Frontmatter Features

- `context: fork` — Run skill in isolated subagent
- `hooks:` — Skill-scoped hooks
- `model:` — Per-skill model selection
- Dynamic context via `!command` syntax

### Path-Specific Rules

`.claude/rules/` supports path-scoped rules:
```yaml
---
paths:
  - "tests/**/*.py"
---
# Testing conventions that only apply to test files
```

---

## The Philosophical Shift

**Sonnet-era:** Skills are procedures. They compensate for the model's limitations. The skill author does the thinking; the model follows instructions.

**Opus-era:** Skills are briefs. They communicate intent, principles, and constraints. The model does the thinking; the skill author sets the guardrails.

This matches Anthropic's guidance: "Be explicit with your instructions" but "add context to improve performance" — tell Opus *why* something matters, not *how* to do it step by step.

---

## Proposed Implementation Phases

Each phase is independently valuable and testable:

1. **Phase 1: Extract rules** — Move config loading, TDD, quality gates, handoffs, vertical slicing to `.claude/rules/`. Immediate token savings, no skill behavior change.

2. **Phase 2: Define agents** — Create `.claude/agents/` for e2e-test-designer, e2e-test-architect, e2e-tester. Makes them real.

3. **Phase 3: Merge and slim design pipeline** — Combine kdesign + kdesign-validate, slim kdesign-impl-plan into /kplan.

4. **Phase 4: Merge and slim execution pipeline** — Combine ktask + kmilestone into /kbuild.

5. **Phase 5: Add hooks** — Post-edit formatting, quality gate checks.

---

## Open Questions for Design Discussion

1. Should `/kbuild` keep the skill invocation boundary between milestone and task (for context management), or truly merge them?
2. How aggressive should we be with the language shift? Pure principles, or keep some structure for complex skills like `/kplan`?
3. Should agent teams be a stretch goal or a separate design?
4. What's the right level of structure for the rules files? Bullet points or prose?
5. Should we prototype one skill first (e.g., `/kreview` trim) before doing the full transformation?
6. How to handle the transition? Rename old skills to `*.bak` or just replace?
