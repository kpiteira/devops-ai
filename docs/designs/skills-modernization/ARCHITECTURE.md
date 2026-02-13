# Skills Modernization: Architecture

**Date:** 2026-02-13
**Status:** Draft

---

## Overview

The modernized skill system has three layers: **rules** (always-loaded principles), **skills** (workflow briefs invoked on demand), and a **test catalog** (reusable E2E test definitions per project). Rules eliminate duplication by extracting shared patterns. Skills become thin briefs that communicate intent and constraints. The test catalog provides structural E2E enforcement.

The system runs within Claude Code's existing infrastructure — `.claude/rules/` for auto-loading, `~/.claude/skills/` symlinks for global skill discovery, and standard markdown files throughout.

---

## Component Diagram

```
~/.claude/
├── skills/                      # Symlinks to devops-ai/skills/
│   ├── kdesign → ...            # Design + architecture + validation
│   ├── kplan → ...              # Implementation planning
│   ├── kbuild → ...             # Task execution + milestone orchestration
│   ├── kreview → ...            # PR review assessment
│   ├── kissue → ...             # Issue implementation
│   ├── kworktree → ...          # Worktree/sandbox management
│   └── kinfra-onboard → ...     # Project onboarding
└── agents/                      # Cleaned (old SDD agents removed)

devops-ai/                       # Source of truth
├── skills/
│   ├── kdesign/skill.md
│   ├── kplan/skill.md
│   ├── kbuild/skill.md
│   ├── kreview/skill.md
│   ├── kissue/skill.md
│   ├── kworktree/skill.md
│   ├── kinfra-onboard/skill.md
│   └── shared/                  # REMOVED (absorbed into rules)
├── rules/                       # Source for per-project .claude/rules/
│   ├── project-config.md
│   ├── tdd.md
│   ├── quality-gates.md
│   ├── handoffs.md
│   ├── vertical-slicing.md
│   └── e2e-testing.md
└── install.sh                   # Updated: symlinks skills + copies rules

<project>/.claude/               # Per-project (created by install/onboard)
├── rules/                       # Auto-loaded by Claude Code
│   ├── project-config.md
│   ├── tdd.md
│   ├── quality-gates.md
│   ├── handoffs.md
│   ├── vertical-slicing.md
│   └── e2e-testing.md
├── skills/                      # Optional project-specific overrides
└── settings.json

<project>/docs/e2e-tests/        # Per-project test catalog
├── README.md                    # Catalog conventions
├── <category>/
│   └── <test-name>.md           # Test definition
```

### Component Relationships

| Component | Type | Depends On | Used By |
|-----------|------|------------|---------|
| Rules (6 files) | `.claude/rules/*.md` | None (auto-loaded) | All skills, all conversations |
| `/kdesign` | Skill | Rules (config, vertical-slicing) | User → produces DESIGN.md, ARCHITECTURE.md |
| `/kplan` | Skill | Rules (config, tdd, quality-gates, vertical-slicing, e2e-testing) | User, consumes kdesign output → produces milestone files |
| `/kbuild` | Skill | Rules (config, tdd, quality-gates, handoffs, e2e-testing) | User, consumes kplan output → produces code + handoffs |
| `/kreview` | Skill | Rules (config, quality-gates) | User → assesses PR comments |
| `/kissue` | Skill | Rules (config, tdd, quality-gates) | User → implements GitHub issues |
| `/kworktree` | Skill | None | User → manages worktrees/sandboxes |
| `/kinfra-onboard` | Skill | None | User → onboards projects |
| Test catalog | Directory | None | `/kbuild` reads/writes test definitions |
| `install.sh` | Script | devops-ai repo | Sets up symlinks + copies rules |

---

## Rules

### How Rules Work (Claude Code Mechanism)

Rules in `.claude/rules/` are loaded into the context window alongside CLAUDE.md content. Two modes:

- **Unconditional** (no `paths:` frontmatter): Loaded into **every conversation**. Always present, always consuming tokens.
- **Path-scoped** (with `paths:` frontmatter): Only loaded when Claude is working with files matching the glob patterns.

All 6 of our rules are **unconditional** (~1,500 tokens total always-on). This is intentional — these are workflow principles (TDD, E2E enforcement) that apply to how you work, not which files you touch. Path-scoping doesn't help because "use TDD" applies before the test files exist.

**Cost/benefit:** ~1,500 tokens always-on vs ~18,000 tokens of duplicated boilerplate eliminated from skills. The main beneficiary is /kbuild (the most-used, most context-heavy skill), which gains all 6 rules without any inline duplication.

### Rule Definitions

### `project-config.md` (~250 tokens)

Config loading from `.devops-ai/project.md`. Replaces the 50-line block duplicated across 9 skills.

**Content:**
- How to find and parse `.devops-ai/project.md`
- What values to extract (project name, test commands, quality commands, paths)
- Fallback behavior when config is missing or malformed
- When to offer config generation (only if user asks)

**Key change from current:** No "Generating Config" section — that procedure stays in skills that might need it (kdesign on first use). The rule just says "load config if it exists, ask if it doesn't."

### `tdd.md` (~200 tokens)

TDD principles. Replaces duplicate sections in ktask and kissue.

**Content:**
- RED: Write failing tests first. Verify they fail meaningfully (not import errors).
- GREEN: Write minimum code to pass tests. Follow existing patterns.
- REFACTOR: Improve clarity. Run tests after each change.
- If you catch yourself writing implementation before tests, stop and return to RED.

### `quality-gates.md` (~200 tokens)

Quality verification. Replaces duplicate checklists in ktask and kmilestone.

**Content:**
- All unit tests pass (use configured command)
- Quality checks pass (use configured command, if configured)
- Code is committed with clear messages
- No security vulnerabilities introduced

### `handoffs.md` (~200 tokens)

Handoff document conventions. Replaces duplicate sections in ktask and kmilestone.

**Content:**
- Update `HANDOFF_*.md` after every task
- Include: gotchas, workarounds, emergent patterns, next-task notes
- Exclude: status info available elsewhere, process steps, test counts
- Target: under 100 lines total

### `vertical-slicing.md` (~200 tokens)

Vertical milestone principles. Replaces duplicate guidance in kdesign-validate and kdesign-impl-plan.

**Content:**
- Each milestone is E2E testable
- Each milestone delivers observable value
- Vertical (across layers) not horizontal (one layer at a time)
- Milestone N builds on milestone N-1

### `e2e-testing.md` (~400 tokens)

Real E2E testing definition and enforcement. Replaces shared/e2e-prompt.md and agent references in 4 skills.

**Content:**
- **Definition:** Real E2E = running infrastructure, real API calls, actual state changes, observable outcomes
- **Not E2E:** imports-without-errors, system-starts-cleanly, mock-based assertions, component-level integration
- **Structural requirement:** Every milestone ends with a VALIDATION task exercising the running system
- **Evidence requirement:** Milestone completion must include what was tested, commands run, output observed
- **Test catalog:** Check `docs/e2e-tests/` for existing tests before designing new ones. Add new tests to catalog after execution.

---

## Skills

Each skill is a markdown file with YAML frontmatter (name, description) and a brief that communicates intent, principles, and constraints. No prescribed step numbers or mandatory pauses.

### `/kdesign` (~200 lines)

**Purpose:** Design exploration, architecture drafting, validation, and milestone structure.

**Replaces:** kdesign (474 lines) + kdesign-validate (608 lines)

**Brief structure:**
- What this produces: DESIGN.md, ARCHITECTURE.md, milestone structure
- This is a conversation: explore problem space, propose options, make decisions together
- Design principles: right-sized design, decisions over description, acknowledge uncertainty
- Architecture principles: Rosetta stone (diagrams + tables), interface signatures not implementations
- Validation: trace scenarios through the architecture, surface gaps as decisions to make
- Conversation patterns that work (from kdesign-validate — genuinely valuable)
- Milestone structure: propose vertical milestones with E2E test scenarios

**What's removed:**
- Steps 1-5 with prescribed pauses → Opus decides when to pause
- Output templates → Opus decides format based on situation
- Config loading boilerplate → now in rule

**What's preserved:**
- Rosetta stone approach (human diagrams + LLM tables)
- Conversation-first philosophy
- Concrete scenario tracing
- Gap analysis as decisions, not reports
- Architecture vs implementation planning distinction

### `/kplan` (~250 lines + reference file)

**Purpose:** Expand validated milestone structure into implementable tasks.

**Replaces:** kdesign-impl-plan (993 lines)

**Brief structure:**
- Architecture alignment: understand and commit to architecture's core patterns before planning
- Expand each milestone into tasks with specific files, acceptance criteria, and test requirements
- Task quality: each task implementable by someone who only reads that task
- One file per milestone (context-manageable)
- Last task of every milestone is VALIDATION type (structural E2E enforcement)

**Reference file:** `kplan-categories.md` — task type categories and failure modes (currently the 50+ line appendix). Loaded on demand, not inline.

**What's removed:**
- Steps 0-6 with prescribed pauses → Opus decides flow
- E2E agent invocation instructions (designer/architect/tester) → replaced by rule
- Pattern examples (async operation, state machine, external integration) → Opus knows these
- Config loading boilerplate → now in rule

**What's preserved:**
- Architecture alignment check (as principle, not rigid Step 0)
- Task specificity requirements ("implementable by someone who only reads that task")
- Task-type categories (in reference file)
- One-file-per-milestone output structure
- Frontmatter for document references
- Consistency self-check (design → plan traceability)

### `/kbuild` (~200 lines)

**Purpose:** Execute tasks with TDD and orchestrate milestones.

**Replaces:** ktask (467 lines) + kmilestone (404 lines)

**Brief structure:**
- **Single task mode:** Research → TDD cycle → verify → handoff
- **Milestone mode:** Sequence tasks, verify between them, produce completion report
- Research before coding: read context docs, find patterns, check handoffs
- Code samples in plans are structure, not implementation
- Milestone completion report format (interface contract for PR creation):
  - E2E tests performed (test, steps, result)
  - Challenges and solutions
  - Failed tests not due to this work

**What's removed:**
- Separate ktask/kmilestone invocation ceremony → single skill handles both
- E2E agent workflow instructions → replaced by rule
- Config loading boilerplate → now in rule
- TDD details → now in rule
- Quality gates details → now in rule
- Handoff details → now in rule
- Anti-patterns tables and guardrails → Opus doesn't need these

**What's preserved:**
- Research phase (read before writing)
- "Code samples are structure, not implementation" warning
- Milestone completion report format (downstream dependency)
- Task classification (CODING, RESEARCH, MIXED, VALIDATION)
- Handoff document requirement (via rule reference)
- Unexpected findings guardrail (brief version)

### `/kreview` (~150 lines)

**Purpose:** Critically assess PR review comments.

**Changes:** Remove config loading boilerplate. Light language trim. Core unchanged — already well-designed.

### `/kissue` (~120 lines)

**Purpose:** Implement GitHub issues with TDD.

**Changes:** Remove config loading boilerplate. Remove TDD section (now in rule). Light language trim. Core workflow unchanged.

### `/kworktree` (~175 lines)

**Changes:** None. Already concise reference material.

### `/kinfra-onboard` (~300 lines)

**Changes:** Light trim. Keep phased structure (appropriate for destructive operations). Remove config loading boilerplate where duplicated.

---

## Test Catalog

Per-project directory for reusable E2E test definitions.

### Location

`docs/e2e-tests/` in each project (or configured path in `.devops-ai/project.md`).

### Structure

```
docs/e2e-tests/
├── README.md              # Conventions for this project
├── workflow/
│   ├── core-cycle.md      # Test: complete workflow cycle
│   └── error-recovery.md  # Test: recovery from mid-workflow failure
├── api/
│   └── health-check.md    # Test: all endpoints respond correctly
└── integration/
    └── otel-traces.md     # Test: traces appear in Jaeger
```

### Test Definition Format

Each test file:
- **Purpose:** One sentence
- **Prerequisites:** What must be running
- **Steps:** Numbered actions with expected results
- **Success criteria:** Observable outcomes
- **Evidence to capture:** Logs, API responses, database state

### Interaction with /kbuild

1. Before designing a new E2E test, /kbuild checks the catalog for existing tests
2. If a matching test exists, /kbuild executes it
3. If no match, /kbuild designs a new test, executes it, and adds it to the catalog
4. The catalog grows organically — no upfront design needed

---

## Cleanup

### Old SDD-Era Agents (Remove)

These agents in `~/.claude/agents/` are from Aug 2025, unused, and should be removed:

| Agent | Created | Reason for Removal |
|-------|---------|--------------------|
| `architecture-specialist.md` | Aug 2025 | Superseded by /kdesign |
| `bundler-specialist.md` | Aug 2025 | SDD-specific, unused |
| `coder-specialist.md` | Aug 2025 | Superseded by /kbuild |
| `milestone-planning-specialist.md` | Aug 2025 | Superseded by /kplan |
| `project_structure_analysis.md` | Aug 2025 | SDD-specific, unused |
| `requirements-specialist.md` | Aug 2025 | SDD-specific, unused |
| `roadmap-specialist.md` | Aug 2025 | SDD-specific, unused |
| `task-blueprint-specialist.md` | Aug 2025 | Superseded by /kplan |
| `validator-specialist.md` | Aug 2025 | Superseded by /kbuild |

### Removed Skill Files

| File | Replacement |
|------|-------------|
| `skills/kdesign-validate/skill.md` | Merged into `skills/kdesign/skill.md` |
| `skills/kdesign-impl-plan/skill.md` | Renamed to `skills/kplan/skill.md` |
| `skills/ktask/skill.md` | Merged into `skills/kbuild/skill.md` |
| `skills/kmilestone/skill.md` | Merged into `skills/kbuild/skill.md` |
| `skills/shared/e2e-prompt.md` | Absorbed into `rules/e2e-testing.md` |

---

## Data Flow

### Design → Plan → Build Cycle

```
User invokes /kdesign
  → Reads: rules (auto-loaded), existing codebase
  → Produces: DESIGN.md, ARCHITECTURE.md, milestone structure
  → Conversation: explores problem, proposes options, validates scenarios

User invokes /kplan
  → Reads: rules (auto-loaded), DESIGN.md, ARCHITECTURE.md, milestone structure
  → Reads: kplan-categories.md (reference, on demand)
  → Produces: OVERVIEW.md, M1_*.md, M2_*.md, ... (one file per milestone)
  → Each milestone file: frontmatter refs, tasks, VALIDATION task at end

User invokes /kbuild
  → Reads: rules (auto-loaded), milestone file, DESIGN.md, ARCHITECTURE.md
  → Reads: docs/e2e-tests/ (test catalog, before VALIDATION task)
  → Single task: Research → TDD → Verify → Handoff
  → Milestone: Sequences tasks → VALIDATION → Completion report
  → Produces: code, tests, handoffs, milestone completion report
  → Updates: test catalog (adds new E2E tests)
```

### Standalone Skills

```
User invokes /kissue
  → Reads: rules (auto-loaded), GitHub issue
  → TDD cycle → PR with "Closes #N"

User invokes /kreview
  → Reads: rules (auto-loaded), PR comments
  → Assesses → Implements/pushes-back/discusses

User invokes /kworktree
  → Reference for kinfra CLI commands (no rules needed)

User invokes /kinfra-onboard
  → 4-phase onboarding (analyze → propose → execute → verify)
```

---

## Installation and Distribution

### `install.sh` Updates

The install script needs to:
1. Symlink skills from `devops-ai/skills/` to `~/.claude/skills/`
2. Remove old symlinks for renamed/removed skills (kdesign-validate, kdesign-impl-plan, ktask, kmilestone, shared)
3. Add new symlinks (kplan, kbuild)
4. Remove old SDD agents from `~/.claude/agents/`

### Per-Project Setup

Rules need to be in each project's `.claude/rules/` directory. Options:
- **Copy:** `install.sh` copies rules to target project's `.claude/rules/`
- **Symlink:** `install.sh` symlinks rules from devops-ai to target project
- **kinfra-onboard:** Onboarding skill copies rules as part of project setup

Symlinks are preferred (single source of truth, updates propagate). The install script should support `install.sh rules <project-path>` to set up rules for a specific project.

---

## Migration Strategy

### Phase 1: Extract Rules
- Create `devops-ai/rules/` with 6 rule files
- Copy/symlink to `.claude/rules/` in devops-ai project
- **No skill changes yet** — rules are additive
- Verify: rules auto-load, skills still work with both rules and inline versions

### Phase 2: Clean Up Old Agents
- Remove 9 old SDD agents from `~/.claude/agents/`
- Verify: no skill references these agents

### Phase 3: Slim Standalone Skills
- Trim kreview: remove config boilerplate
- Trim kissue: remove config boilerplate + TDD section
- Light trim kinfra-onboard
- Verify: each skill works with rules providing shared context

### Phase 4: Merge Design Pipeline
- Create new kdesign (merged kdesign + kdesign-validate)
- Create new kplan (slimmed kdesign-impl-plan + reference file)
- Remove old kdesign-validate, kdesign-impl-plan
- Update symlinks
- Verify: /kdesign produces DESIGN.md + ARCHITECTURE.md + milestones

### Phase 5: Merge Execution Pipeline
- Create new kbuild (merged ktask + kmilestone)
- Remove old ktask, kmilestone, shared/e2e-prompt.md
- Update symlinks
- Verify: /kbuild handles single tasks and milestones

### Phase 6: Update Install Script
- Update install.sh for new skill names and rules distribution
- Test clean install on a fresh project

### Phase Order Rationale

Phases 1-2 are risk-free (additive changes, cleanup). Phase 3 is low-risk (removing duplication, not changing behavior). Phases 4-5 are the substantive changes — by this point, rules are providing shared context, so the merged skills can be thin. Phase 6 finalizes distribution.

Each phase is independently committable and testable. If a phase reveals issues, we can pause without blocking other work.

---

## Verification Approach

| Component | How to Verify |
|-----------|---------------|
| Rules | Invoke a skill, check that rules context is available without duplication |
| `/kdesign` | Run against a real design problem, verify produces DESIGN.md + ARCHITECTURE.md + milestones |
| `/kplan` | Run against kdesign output, verify produces milestone files with tasks |
| `/kbuild` | Run against a milestone file, verify TDD cycle + completion report |
| `/kreview` | Run against a PR with comments, verify assessment + action |
| `/kissue` | Run against a GitHub issue, verify TDD + PR creation |
| Token budget | Count tokens in new skills vs old — target 69% reduction |
| Old agents | Verify `~/.claude/agents/` only contains intentional agents |
| E2E enforcement | Run /kbuild on a milestone — verify VALIDATION task is executed with evidence |
