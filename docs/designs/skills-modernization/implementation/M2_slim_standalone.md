---
design: docs/designs/skills-modernization/DESIGN.md
architecture: docs/designs/skills-modernization/ARCHITECTURE.md
---

# Milestone 2: Slim Standalone Skills

**Goal:** kreview, kissue, and kinfra-onboard are trimmed — config boilerplate removed (now in rules), language shifted to principled, token budgets hit.

**Branch:** `impl/skills-modernization`
**Builds on:** M1 (rules must exist)

---

## Task 2.1: Trim kreview

**File(s):**
- `skills/kreview/SKILL.md` (modify)

**Type:** CODING
**Estimated time:** 1 hour

**Description:**
Remove config loading boilerplate (now provided by `project-config.md` rule). Shift any remaining prescriptive language to principled. kreview is already well-designed — this is a light trim.

**Implementation Notes:**

kreview's config section (lines 27-34) is already brief — just 8 lines saying "read config, ask if missing." Replace with a one-liner referencing the rule: the rule is auto-loaded, so the skill just needs to say "Use project config for test/quality commands."

Scan for remaining aggressive language patterns:
- "DO NOT" → soften or remove if the principle is in a rule
- "MUST" / "NEVER" → normal language

Keep the core assessment framework intact — it's already principled and well-structured.

**Before:** 283 lines
**Target:** ~150 lines

**Acceptance Criteria:**
- [ ] Config loading boilerplate removed (no duplicate of project-config.md rule)
- [ ] No "CRITICAL", "MANDATORY" language
- [ ] Core assessment framework (IMPLEMENT/PUSH BACK/DISCUSS) preserved
- [ ] Reviewer comparison section preserved
- [ ] ~150 lines (±20)
- [ ] Skill still invocable and produces reasonable output

---

## Task 2.2: Trim kissue

**File(s):**
- `skills/kissue/SKILL.md` (modify)

**Type:** CODING
**Estimated time:** 1 hour

**Description:**
Remove config loading boilerplate (lines 12-29, now in rules). Remove TDD details (lines 124-148, now in `tdd.md` rule). Keep the workflow structure (fetch → setup → research → implement → verify → complete).

**Implementation Notes:**

Two blocks to remove:
1. **Config loading** (lines 12-29): Replace with brief reference — the `project-config.md` rule handles this
2. **TDD details** (lines 124-148): The `tdd.md` rule provides RED→GREEN→REFACTOR. Skill just needs to say "Implement using TDD" and reference the rule implicitly

Keep:
- GitHub issue fetch workflow (kissue's unique value)
- Branch creation from issue
- PR creation with "Closes #N"
- Error handling table

Shift language from prescriptive to principled where found.

**Before:** 267 lines
**Target:** ~120 lines

**Acceptance Criteria:**
- [ ] Config loading boilerplate removed
- [ ] TDD section removed (rule provides it)
- [ ] GitHub workflow preserved (fetch, branch, PR)
- [ ] ~120 lines (±20)
- [ ] Skill still invocable and produces reasonable output

---

## Task 2.3: Trim kinfra-onboard

**File(s):**
- `skills/kinfra-onboard/SKILL.md` (modify)

**Type:** CODING
**Estimated time:** 1 hour

**Description:**
Light trim. Keep the phased structure (appropriate for destructive operations — analyze → propose → execute → verify). Remove any config boilerplate duplication. Soften prescriptive language.

**Implementation Notes:**

kinfra-onboard's phased structure is intentionally prescriptive because it modifies compose files and config — destructive operations that need explicit user approval gates. The phases stay.

Trim opportunities:
- Config loading section if any overlaps with project-config.md rule
- Error handling table — compact if verbose
- Example session — keep but trim if long
- Shared observability reference table — keep (unique, factual)

This is the lightest trim of the three.

**Before:** 373 lines
**Target:** ~300 lines

**Acceptance Criteria:**
- [ ] Phased structure preserved (analyze → propose → execute → verify)
- [ ] User approval gate before Phase 3 preserved
- [ ] Rollback procedure preserved
- [ ] ~300 lines (±30)
- [ ] Skill still invocable

---

## Task 2.4: Validate Trimmed Skills

**Type:** VALIDATION
**Estimated time:** 15 min

**Description:**
Verify each trimmed skill works correctly with rules providing shared context.

**Verification Steps:**

1. **Structural checks:**
   ```bash
   # Line counts
   wc -l skills/kreview/SKILL.md    # Target: ~150
   wc -l skills/kissue/SKILL.md     # Target: ~120
   wc -l skills/kinfra-onboard/SKILL.md  # Target: ~300

   # No residual config boilerplate (the full block)
   grep -l "Inspect the project root.*for project type indicators" skills/kreview/SKILL.md skills/kissue/SKILL.md
   # Should return nothing

   # No aggressive language
   grep -c "CRITICAL\|MANDATORY" skills/kreview/SKILL.md skills/kissue/SKILL.md
   # Should be 0 for each
   ```

2. **Functional check:**
   - Invoke `/kreview` on an existing PR — verify it fetches comments, assesses, categorizes
   - Or: verify the skill loads without errors and the workflow description is coherent

3. **Token savings:**
   - Before: kreview (283) + kissue (267) + kinfra-onboard (373) = 923 lines
   - After: ~150 + ~120 + ~300 = ~570 lines
   - Savings: ~38%

**Acceptance Criteria:**
- [ ] All 3 trimmed skills are under target line counts
- [ ] No residual config loading boilerplate in trimmed skills
- [ ] No aggressive enforcement language
- [ ] At least one skill functionally verified (invoke on real scenario)

---

## Milestone 2 Completion Checklist

- [ ] All tasks complete and committed
- [ ] kreview, kissue, kinfra-onboard trimmed to target sizes
- [ ] No config boilerplate duplication (rules provide it)
- [ ] Skills work with rules in context
