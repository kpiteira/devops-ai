---
name: kplan
description: Expand milestones into implementable tasks with architecture alignment, TDD requirements, and E2E validation.
---

# Implementation Planning Command

Expand milestones from a design into detailed, implementable tasks. Each task is self-contained — someone reading only that task should be able to implement it.

## What This Produces

- **OVERVIEW.md** — Milestone summary, dependency graph, branch strategy
- **One file per milestone** (M1_name.md, M2_name.md, ...) — detailed tasks with files, acceptance criteria, and tests

## Command Usage

```
/kplan design: <DESIGN.md> arch: <ARCHITECTURE.md> [validation: <SCENARIOS.md>]
```

If validation output exists, use its scenarios and milestone structure as the starting point.

---

## This is a Conversation

Claude proposes milestones and tasks, but:
- Claude may miss dependencies. You know what's flaky and what has hidden complexity.
- Claude may over-split or under-split. You know team capacity and what makes sense as a unit.
- Milestone boundaries are judgment calls. Claude proposes, you adjust.

---

## Architecture Alignment

Before planning any tasks, understand the architecture's core decisions. This prevents implementation drift — the most common and expensive planning failure.

Read the architecture document and extract:
- **Core patterns** — What architectural approaches are used (state machine, event-driven, worker model, etc.) and how they'll be implemented
- **Key decisions** — What was decided and what it means for task design
- **What's ruled out** — Approaches explicitly rejected in the architecture

Share these with the user for confirmation before proceeding. If the architecture says "state machine with explicit transitions," no task should use a polling loop instead.

Every task should trace back to an architectural decision. If a task introduces a pattern not in the architecture, either update the architecture or remove the task.

---

## Task Expansion

For each milestone, create tasks with:

### Task Structure

```markdown
## Task N.M: [Title]

**File(s):** [Specific files to create/modify]
**Type:** CODING | RESEARCH | MIXED | VALIDATION
**Estimated time:** [1-4 hours]

**Description:**
[What this task accomplishes — specific about behavior, not just "implement X"]

**Implementation Notes:**
[Patterns to follow, gotchas, integration points]

**Testing Requirements:**
- [ ] [Specific test cases — happy path, errors, edge cases]

**Acceptance Criteria:**
- [ ] [Verifiable criterion]
```

### Task Quality

Each task should be implementable by someone who only reads that task:

- **Files named** — not "update the service" but "modify `src/services/user.py`"
- **Behavior described** — not "add validation" but "validate symbol exists in cache before starting download"
- **Tests specified** — not "add tests" but "test: returns 404 if symbol not found"
- **Patterns referenced** — not "follow existing patterns" but "follow pattern in `UserService.create()`"

Tasks estimated at >4 hours should be split.

### Task Type Analysis

For tasks touching multiple categories (persistence, wiring, state machines, etc.), identify the failure modes specific to each category and add corresponding integration tests. The reference file `kplan-categories.md` has the full taxonomy — load it when analyzing task types.

---

## VALIDATION Tasks

Every milestone ends with a VALIDATION task. This is a structural requirement, not optional.

The VALIDATION task exercises the real system end-to-end to verify the milestone works as designed. The `e2e-testing` rule defines what "real E2E" means and what makes a valid validation.

A validation that only checks "does it start" is insufficient. Valid tests exercise real operational flows with verifiable outcomes.

---

## Output Structure

Implementation plans live next to the design documents:

```
docs/designs/<feature>/
  DESIGN.md
  ARCHITECTURE.md
  implementation/
    OVERVIEW.md
    M1_<name>.md
    M2_<name>.md
    ...
```

### Frontmatter

Each milestone file includes frontmatter referencing the design and architecture docs. This enables `/kbuild` to automatically discover context documents.

```markdown
---
design: docs/designs/<feature>/DESIGN.md
architecture: docs/designs/<feature>/ARCHITECTURE.md
---
```

### Consistency Check

Before saving the plan, verify:
- Every major design decision appears in at least one task
- Every architectural pattern has implementing tasks
- No task introduces an approach ruled out by the architecture
- The dependency ordering is correct

---

## Integration

This command sits between `/kdesign` (which produces the design) and `/kbuild` (which executes the tasks). The milestone files are the interface contract between planning and execution.
