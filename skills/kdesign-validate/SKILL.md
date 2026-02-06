---
name: kdesign-validate
description: Validate design documents through scenario tracing, gap analysis, and interface contracts before implementation. Use after design is complete.
metadata:
  version: "0.1.0"
---

# Design Validation Command

## Purpose

Validate a design by walking through concrete scenarios before implementation begins. This catches architectural gaps, state machine inconsistencies, and integration issues *before* code is written.

**When to use:** After design and architecture docs are "complete" but before writing the implementation plan.

**What it produces:**
- Validated scenarios with traced execution paths
- Identified gaps and open questions requiring resolution
- Interface contracts (signatures, data shapes, state transitions)
- Vertical milestone structure for implementation

---

## Configuration Loading

**FIRST STEP — Do this before any workflow action.**

1. Read `.devops-ai/project.md` from the project root
2. If the file exists, extract:
   - **Project.name** — used in document headers and context
   - **Paths.design_documents** — where design docs are stored
3. If the file does NOT exist:
   - Ask: "Where do you store design documents?" (default: `docs/designs/`)
   - Ask: "What's the project name?"
   - Proceed with answers
   - Suggest: "Would you like me to create a `.devops-ai/project.md` so future sessions pick up these values automatically?"
4. Use the configured values throughout this workflow

---

## This is a Conversation, Not a Report

**The command produces scaffolding. The value comes from the conversation.**

Claude will systematically enumerate scenarios and trace through them, but:

- **Claude will miss scenarios.** The most insidious bugs come from scenarios Claude doesn't think of — infrastructure failures, race conditions, recovery flows. You add these.
- **Claude will miss context.** You know what failed before, what's flaky in the codebase, what "feels wrong." This context is essential.
- **Gaps require decisions.** Claude identifies options and trade-offs. You decide.

The command pauses for conversation at each step. Claude asks questions, proposes scenarios, and waits for feedback before proceeding. This back-and-forth is how the validation works.

---

## How We Work Together

This is a collaborative validation, not a rubber stamp. You bring domain knowledge and intuition about what matters. Claude brings systematic scenario analysis and fresh eyes on gaps. Together we stress-test the design before committing to implementation.

**On finding gaps:** These are valuable discoveries, not failures. Every gap found now is hours saved later.

**On ambiguity:** When the design is ambiguous, Claude surfaces the ambiguity with options. You decide.

**On scope:** We validate what's in scope for the current implementation, not the full north star vision.

**On pushing back:** If Claude's scenarios seem shallow or miss the point, say so. The best gaps often come from "what about when X happens?" questions that Claude didn't consider.

---

## Command Usage

```
/kdesign-validate design: <design-doc.md> arch: <architecture-doc.md> [scope: <scope-description>]
```

**Required:**
- `design:` — The design/spec document
- `arch:` — The architecture document

**Optional:**
- `scope:` — What subset of the design to validate (e.g., "MVP Phase 1-2" or "core workflow only")
- Additional reference docs can be included

---

## Validation Process

### Step 1: Scenario Enumeration

Claude reads the design and architecture docs, then proposes 8-12 concrete scenarios covering:

**Happy paths (3-4 scenarios):**
- The primary use case working end-to-end
- Key variations (different inputs, configurations)

**Error paths (2-3 scenarios):**
- Expected failures (validation errors, gate failures)
- Recovery flows (retry, resume, rollback)

**Edge cases (2-3 scenarios):**
- Cancellation at various points
- Concurrent operations
- State transitions that might be ambiguous

**Integration boundaries (1-2 scenarios):**
- Cross-component communication
- External system interactions

**Output format:**
```markdown
## Proposed Scenarios

### Happy Paths
1. **[Scenario Name]**: [One sentence description]
2. ...

### Error Paths
3. **[Scenario Name]**: [One sentence description]
4. ...

### Edge Cases
5. **[Scenario Name]**: [One sentence description]
6. ...

### Integration Boundaries
7. **[Scenario Name]**: [One sentence description]
8. ...
```

---

**Pause: Scenario Review**

After proposing scenarios, Claude pauses and asks:

> "These are my proposed scenarios. Before I trace through them:
>
> 1. **What's missing?** What failure modes have you seen before? What keeps you up at night about this design?
> 2. **What's not worth tracing?** Any scenarios here that are obvious or low-risk?
> 3. **What's the scary scenario?** The one that feels like it could bite us — even if you can't articulate exactly why?
>
> I'd rather trace 5 scenarios that matter than 12 that don't."

The scenarios you add here are often the most valuable ones — they come from lived experience with the codebase and past failures. This is where Claude's systematic approach meets your institutional knowledge.

---

### Step 2: Scenario Walk-Through

For each approved scenario, Claude traces through the architecture step-by-step:

**For each step:**
- Which component handles this?
- What is the input (data shape, state)?
- What processing occurs?
- What is the output (data shape, state change)?
- What could go wrong?

**Output format:**
```markdown
## Scenario: [Name]

**Trigger:** [What initiates this scenario]
**Expected Outcome:** [What success looks like]

### Execution Trace

| Step | Component | Action | Input | Output | State Change | Verification |
|------|-----------|--------|-------|--------|--------------|--------------|
| 1 | [Component] | [Action] | [Input] | [Output] | [State change] | [Test type needed] |
| 2 | ... | ... | ... | ... | ... | ... |

### Questions / Gaps Identified

- **[Q1]**: [Question about ambiguity or missing detail]
- **[GAP]**: [Something the design doesn't cover]
- **[VERIFY]**: [Verification approach needed for this component type]
```

The **Verification** column surfaces test requirements during design validation, not during implementation. For each step, ask:
- Does this component store data? → DB verification needed
- Does this use dependency injection? → Wiring test needed
- Is this a background task? → Lifecycle test needed

**Key questions Claude asks during walk-through:**
- "What happens if this fails?" (for each step)
- "What state is the system in if we stop here?"
- "How does component A know about state change in component B?"
- "Is this synchronous or async? What are the implications?"

---

### Step 3: Gap Analysis

After all scenarios are traced, Claude consolidates findings:

**Gap Categories:**

1. **State Machine Gaps** — Transitions not covered
   - "What state is the entity in after step A completes but before step B starts?"
   - "Can this entity be cancelled while in QUEUED state?"

2. **Error Handling Gaps** — Failures without defined behavior
   - "What happens if the write succeeds but the DB insert fails?"
   - "How does the system recover from a partial save?"

3. **Data Shape Gaps** — Undefined or ambiguous data
   - "What fields are in the metadata JSON?"
   - "What's the format of the result summary?"

4. **Integration Gaps** — Unclear component boundaries
   - "Who owns the decision to retry vs. fail?"
   - "How does component B know which state to load?"

5. **Concurrency Gaps** — Race conditions or ordering issues
   - "What if two operations fire simultaneously?"
   - "Can a cancel arrive while a save is being written?"

6. **Infrastructure Gaps** — Deployment, restart, recovery issues
   - "What happens on service restart mid-operation?"
   - "How are orphaned operations cleaned up?"

7. **Verification Gaps** — Missing integration/smoke tests for component types
   - "This component stores data but no DB verification is specified"
   - "This component uses DI but no wiring test is specified"
   - "This component runs async but no lifecycle test is specified"

**Output format:**
```markdown
## Gap Analysis

### Critical (Must Resolve Before Implementation)

**[GAP-1]: [Title]**
- **Category:** State Machine
- **Scenario:** [Which scenario exposed this]
- **Issue:** [Description]
- **Options:**
  - A) [Option with trade-offs]
  - B) [Option with trade-offs]
- **Recommendation:** [Claude's suggestion]

### Important (Should Resolve, May Defer)

**[GAP-2]: [Title]**
...

### Minor (Note for Implementation)

**[GAP-3]: [Title]**
...
```

---

**Pause: Gap Resolution**

After presenting gaps, Claude works through each critical gap:

> "I found [N] critical gaps that need decisions before we proceed.
>
> Let's work through them one at a time:
>
> **[GAP-1]: [Title]**
> [Explanation of the issue]
>
> Options:
> - A) [Option] — [Trade-offs]
> - B) [Option] — [Trade-offs]
>
> I'm leaning toward [X] because [reasoning]. What's your take?
>
> Also — does this gap remind you of anything that's bitten you before?"

**For each critical gap:**
- Claude presents options and trade-offs
- Claude gives a recommendation with reasoning
- You decide (or ask for more analysis)
- Decision is recorded

This is where the real value happens. The gap analysis is just setup for the conversation. Your decisions turn vague gaps into concrete constraints.

---

### Step 4: Interface Contracts

Based on the scenario traces and gap resolutions, Claude produces concrete interface specifications:

**API Endpoints** (if applicable):
```markdown
### POST /resource/action

**Request:**
```json
{
  "field": "value"
}
```

**Response (202 Accepted):**
```json
{
  "id": "...",
  "status": "started"
}
```

**Error Responses:**
- 409 Conflict: [condition]
- 503 Service Unavailable: [condition]
```

**State Transitions** (if applicable):
```markdown
### Entity State Machine

```
INITIAL
  ├─[trigger: start]─→ PROCESSING

PROCESSING
  ├─[event: complete, gate: PASS]─→ NEXT_PHASE
  ├─[event: complete, gate: FAIL]─→ INITIAL (outcome: FAILED_GATE)
  ├─[event: error]─→ INITIAL (outcome: FAILED)
  ├─[event: cancelled]─→ INITIAL (outcome: CANCELLED)
...
```
```

**Data Shapes** (if applicable):
```markdown
### EntityData

```python
@dataclass
class EntityData:
    id: str
    type: Literal["type_a", "type_b"]
    created_at: datetime
    # ... fields discovered during validation
```
```

---

### Step 5: Vertical Milestone Structure

Finally, Claude proposes an implementation structure organized as vertical slices, not horizontal layers.

**Principles:**
- Each milestone is E2E testable
- Each milestone builds on the previous
- Each milestone delivers user-visible value (or proves a critical path)

**Output format:**
```markdown
## Implementation Milestones

### Milestone 1: [Name] — [What's E2E Testable]

**User Story:** As a [user], I can [action] and see [result].

**Scope:**
- [Component A]: [What's built]
- [Component B]: [What's built]
- [Component C]: [Minimal/stub if needed]

**E2E Test:**
```
Given: [Initial state]
When: [User action]
Then: [Observable result]
```

**Estimated Effort:** [X days]

**Depends On:** [Previous milestone or nothing]

---

### Milestone 2: [Name] — [What's E2E Testable]
...
```

**Example transformation (from horizontal to vertical):**

Horizontal (problematic):
```
Phase 1: All database tables
Phase 2: All service layer code
Phase 3: All API endpoints
Phase 4: Integration testing
```

Vertical (better):
```
Milestone 1: "User can trigger action and see result saved"
  - DB: primary table only
  - Service: core service (minimal)
  - API: trigger endpoint, status endpoint
  - E2E: Trigger → process completes → result exists

Milestone 2: "User can see progress during processing"
  - DB: Add progress columns
  - Service: Progress tracking
  - API: No changes (status already shows progress)
  - E2E: Trigger → progress visible → completes

Milestone 3: "User can see full workflow complete"
  - DB: Add remaining columns
  - Service: Full pipeline integration
  - API: No changes
  - E2E: Trigger → full pipeline → assessment
```

---

## Final Output

At the end of validation, Claude produces a summary document:

```markdown
# Design Validation: [Project Name]

**Date:** [Date]
**Documents Validated:**
- Design: [filename]
- Architecture: [filename]
- Scope: [what was validated]

## Validation Summary

**Scenarios Validated:** X/Y passed
**Critical Gaps Found:** N (all resolved)
**Interface Contracts:** Defined for [list]

## Key Decisions Made

These decisions came from our conversation and should inform implementation:

1. **[Decision]**: [What was decided and why]
   - Context: [What gap or question prompted this]
   - Trade-off accepted: [What we're giving up]

2. ...

## Scenarios Added by User

These scenarios weren't in the initial enumeration but proved important:

1. **[Scenario]**: [Why it mattered]
2. ...

## Remaining Open Questions

To be resolved during implementation:

1. **[Question]**: [Context]
2. ...

## Recommended Milestone Structure

[Summary of milestones with effort estimates]

## Appendix

- Full scenario traces (for reference)
- Complete interface contracts
- Gap analysis details
```

### What Gets Saved

**Save to repo (scenarios.md):**
- Final scenario list (including user's additions)
- Key decisions with rationale
- Interface contracts
- Milestone structure

**Don't save (conversation artifacts):**
- Gap analysis details (gaps are resolved, decisions captured above)
- Walk-through traces (working material)
- Back-and-forth discussion

The saved artifact should be useful for:
- Future sessions ("why did we decide X?")
- Onboarding ("what is this system supposed to do?")
- Testing ("what scenarios should we cover?")

---

## When Validation Fails

Sometimes validation reveals that the design needs significant rework. Signs of this:

- **More than 5 critical gaps** — The design is underspecified
- **Scenarios can't be traced** — The architecture is too vague
- **Circular dependencies** — Components depend on each other in ways that can't be resolved
- **Missing core capability** — A fundamental piece isn't designed

In these cases, Claude should say:

> "This design has [N] critical gaps that suggest it needs another iteration before implementation planning. The main issues are [X, Y, Z]. I recommend we [specific action] before proceeding."

This is valuable! It's much better to discover this now than after writing code.

---

## Conversation Patterns That Work

Based on experience, these conversation patterns produce the best results:

### Pattern 1: "What keeps you up at night?"

After proposing scenarios, ask what feels risky even if it's hard to articulate. The answer often reveals scenarios Claude would never think of.

### Pattern 2: "What's the constraint?"

When a gap has multiple options, ask for the real constraint. The answer often simplifies the decision dramatically.

**Example:**
> Claude: "We could persist operations to DB, or add startup cleanup, or..."
> User: "I'm comfortable losing state on restart. I just don't want inconsistencies."
> Claude: [Now knows the constraint is consistency, not durability — changes the analysis]

### Pattern 3: "Does this remind you of anything?"

Past failures are the best predictor of future failures. When a gap surfaces, ask if it's familiar.

### Pattern 4: "Let me trace that"

When the user adds a scenario, trace it immediately even if it seems simple. The act of tracing often reveals surprises.

### Pattern 5: "What would you need to see?"

When the user is uncertain about a decision, ask what information would help.

**Example:**
> User: "I'm not sure if we need operation persistence..."
> Claude: "What would you need to see to decide? Should I trace what happens without it?"
> User: "Yes, show me the failure mode"
> Claude: [Traces, shows concrete problem, user decides]

---

## Integration with Implementation Planning

After validation completes, the milestone structure becomes the input to implementation planning. Each milestone can be expanded into tasks:

```
Milestone 1 → Phase 1 tasks (with TDD, acceptance criteria, etc.)
Milestone 2 → Phase 2 tasks
...
```

The key difference: tasks within a milestone are all working toward one E2E-testable outcome, not building horizontal layers.

---

## Why This Works (And What Doesn't)

### What makes validation effective:

1. **Concrete scenarios, not abstract review** — "What happens when X" is testable. "Is the design good" is not.

2. **Conversation, not checklist** — Claude's initial scenarios are scaffolding. The real value comes from your additions and decisions.

3. **Traced execution, not hand-waving** — Writing out "Step 1: Component A does X, Step 2: Component B receives Y" forces precision. Gaps become obvious.

4. **Decisions recorded** — "I'm comfortable losing state on restart" is a constraint that shapes everything. Without recording it, the next session won't know.

### What doesn't work:

1. **Running it without engagement** — If you just say "looks good" to every checkpoint, the validation is useless. The value is in the pushback.

2. **Skipping scenarios to save time** — The "boring" scenarios (happy path) are quick to trace. The interesting ones (infrastructure failure) take time but find real bugs.

3. **Treating gaps as failures** — Finding gaps is the point. A validation that finds nothing is suspicious.

4. **Over-documenting** — The conversation matters more than the artifact. Save decisions and scenarios, not every trace.
