---
design: docs/designs/skills-modernization/DESIGN.md
architecture: docs/designs/skills-modernization/ARCHITECTURE.md
---

# Milestone 3: Merge Design Pipeline

**Goal:** `/kdesign` (merged kdesign + kdesign-validate) and `/kplan` (slimmed kdesign-impl-plan) replace 3 old skills.

**Branch:** `impl/skills-modernization`
**Builds on:** M2 (trimming pattern proven, rules providing context)

**Note:** Old skills (kdesign-validate, kdesign-impl-plan) remain available as fallback until Task 3.3 validates the replacements. Only then does Task 3.4 remove them.

---

## Task 3.1: Create New /kdesign

**File(s):**
- `skills/kdesign/skill.md` (rewrite)

**Type:** CODING
**Estimated time:** 2-3 hours

**Description:**
Rewrite kdesign to merge design exploration, architecture drafting, scenario validation, gap resolution, and milestone structure proposal into a single skill brief. This replaces both the old kdesign (474 lines) and kdesign-validate (608 lines).

**Implementation Notes:**

The merged skill communicates intent and principles, not step-by-step procedures.

**What to preserve (from kdesign):**
- Conversation-first philosophy ("this is a conversation, not a generator")
- Design vs architecture distinction (DESIGN.md = what and why, ARCHITECTURE.md = how)
- Rosetta stone approach (diagrams for humans, tables for LLMs)
- Architecture doc principles (interface signatures not implementations, right level of detail)
- "When design isn't needed" section (skip for small/obvious changes)

**What to preserve (from kdesign-validate):**
- Scenario tracing through architecture
- Gap analysis as decisions to make (not problems to report)
- Conversation patterns ("what keeps you up at night?", "what's the constraint?", "does this remind you of anything?")
- Interface contracts (API endpoints, state transitions, data shapes)
- "When validation fails" guidance (>5 critical gaps = needs rework)

**What to add (from architecture decision):**
- Milestone structure proposal at the end (previously in kdesign-validate)
- Vertical slicing principle is in rules, but skill should reference producing milestones

**What to remove:**
- Config loading boilerplate (rule provides it)
- Prescribed Step 1-5 with numbered pauses
- Output templates (Opus decides format)
- Rigid scenario count ("8-12 scenarios")
- Prescribed pause dialog templates
- "Next Steps" section pointing to kdesign-validate (no longer exists)

**Structure of new skill:**
```
Frontmatter (name, description)
Purpose: what this produces (DESIGN.md, ARCHITECTURE.md, milestone structure)
This is a conversation (brief philosophy)
What to explore:
  - Problem space (understand before solving)
  - Solution options (trade-offs, not just one approach)
  - Architecture (components, data flow, state, errors)
  - Validation (trace scenarios, find gaps, resolve as decisions)
  - Milestones (propose vertical slices)
Design principles (right-sized, decisions over description, acknowledge uncertainty)
Architecture principles (Rosetta stone, interface signatures, level of detail)
Conversation patterns (the 5 patterns from kdesign-validate)
Output files (where to save, naming convention)
```

**Before:** 474 + 608 = 1,082 lines (2 skills)
**Target:** ~200 lines (1 skill)

**Acceptance Criteria:**
- [ ] Single skill.md replaces both kdesign and kdesign-validate
- [ ] No prescribed step numbers or mandatory pauses
- [ ] No output templates (Opus decides format)
- [ ] Rosetta stone approach preserved
- [ ] Conversation patterns preserved
- [ ] Milestone structure output described
- [ ] Config boilerplate absent (rule provides it)
- [ ] ~200 lines (±30)

---

## Task 3.2: Create New /kplan + Reference File

**File(s):**
- `skills/kplan/skill.md` (create)
- `skills/kplan/kplan-categories.md` (create)

**Type:** CODING
**Estimated time:** 2-3 hours

**Description:**
Create /kplan as a slimmed version of kdesign-impl-plan. The core value stays: architecture alignment, vertical milestone expansion into tasks, task specificity requirements. The 50+ line task-type-categories appendix moves to a reference file loaded on demand.

**Implementation Notes:**

**What to preserve:**
- Architecture alignment check (the single most valuable thing in the old skill — prevents implementation drift)
- Task specificity requirements ("implementable by someone who only reads that task")
- One-file-per-milestone output structure
- Frontmatter for document references (interface contract for /kbuild)
- Consistency self-check (design → plan traceability)
- Task structure format (compatible with /kbuild consumption)
- VALIDATION task at end of every milestone (structural E2E enforcement)

**What to move to reference file:**
- Task type categories table (Appendix from old skill, lines 940-993)
- Failure modes by category
- Required tests by failure mode
- Smoke test patterns

**What to remove:**
- Config loading boilerplate (rule provides it)
- Steps 0-6 with prescribed pauses → principles with natural flow
- E2E agent invocation instructions (designer/architect/tester) → rule provides E2E definition, catalog provides reuse
- Pattern examples (async operation, state machine, external integration) → Opus knows these
- Red flags tables → Opus can identify issues without checklists
- Common architecture drift examples → the alignment principle is sufficient

**Structure of new skill:**
```
Frontmatter (name, description)
Purpose: expand milestones into implementable tasks
Architecture alignment: understand the architecture before planning (principle, not rigid Step 0)
Task expansion: for each milestone, create tasks with files, acceptance criteria, tests
Task quality: each task self-contained, files named, behavior described, tests specified
Output: one file per milestone, OVERVIEW.md, frontmatter with doc references
VALIDATION task: every milestone ends with E2E validation (reference e2e-testing rule)
Reference: load kplan-categories.md for task type analysis when useful
```

**Reference file (`kplan-categories.md`):**
- Category identification table
- Failure modes by category
- Required tests by failure mode
- Smoke test patterns
- This is loaded on demand by /kplan, not always in context

**Before:** 993 lines (1 skill)
**Target:** ~250 lines (skill) + ~100 lines (reference file)

**Acceptance Criteria:**
- [ ] skill.md captures architecture alignment, task quality, output structure
- [ ] kplan-categories.md contains task type taxonomy
- [ ] No prescribed step numbers or mandatory pauses
- [ ] Architecture alignment preserved as principle
- [ ] Task specificity requirements preserved
- [ ] VALIDATION task requirement stated (references e2e-testing rule)
- [ ] Frontmatter format documented (interface contract)
- [ ] ~250 lines skill + ~100 lines reference (±30 each)

---

## Task 3.3: Validate Design Pipeline

**Type:** VALIDATION
**Estimated time:** 30-45 min

**Description:**
Verify /kdesign and /kplan are discoverable and functional. Dogfood /kdesign on a real problem to validate it produces good design output. Old skills still exist as fallback — this validation proves the replacements work before we remove them in Task 3.4.

**Implementation Notes:**

Create the /kplan symlink now so it's discoverable, but keep old symlinks alive:
```bash
# Add new symlink (old ones still exist)
ln -sfn /Users/karl/Documents/dev/devops-ai/skills/kplan ~/.claude/skills/kplan
```

**Verification Steps:**

1. **Structural checks:**
   ```bash
   # New skills exist
   ls skills/kdesign/skill.md skills/kplan/skill.md skills/kplan/kplan-categories.md

   # Line counts
   wc -l skills/kdesign/skill.md   # Target: ~200
   wc -l skills/kplan/skill.md     # Target: ~250
   wc -l skills/kplan/kplan-categories.md  # Target: ~100

   # No residual boilerplate
   grep -c "Inspect the project root.*for project type indicators" skills/kdesign/skill.md
   # Should be 0
   ```

2. **Token savings:**
   - Before: kdesign (474) + kdesign-validate (608) + kdesign-impl-plan (993) = 2,075 lines
   - After: ~200 + ~250 + ~100 = ~550 lines
   - Savings: ~73%

3. **Dogfood /kdesign on a real problem:**
   - Start a fresh conversation in a project that has pending design work
   - Invoke `/kdesign` on that feature — go through the full design conversation
   - Evaluate: Does the skill guide a productive design conversation? Does it produce useful DESIGN.md + ARCHITECTURE.md? Does it propose milestone structure?
   - If the skill feels wrong (too vague, missing guidance, confusing flow), fix it before proceeding to Task 3.4
   - Note: The design output doesn't need to be perfect — we're validating the skill, not the feature

4. **Verify /kplan loads:**
   - Invoke `/kplan` — verify it's discoverable and the brief loads
   - Verify it describes architecture alignment, task quality, and output structure

**Acceptance Criteria:**
- [ ] /kdesign discoverable and loadable
- [ ] /kplan discoverable and loadable
- [ ] New skills meet line count targets
- [ ] /kdesign dogfooded on a real design problem — produced useful output
- [ ] Old skills still exist (not yet removed — fallback available)

---

## Task 3.4: Remove Old Design Skills

**File(s):**
- `skills/kdesign-validate/` (delete directory)
- `skills/kdesign-impl-plan/` (delete directory)
- `~/.claude/skills/kdesign-validate` (remove symlink)
- `~/.claude/skills/kdesign-impl-plan` (remove symlink)

**Type:** CODING
**Estimated time:** 10 min

**Description:**
Now that Task 3.3 has validated the replacements work, remove the old skill directories and stale symlinks.

**Implementation Notes:**

```bash
# Remove old skill directories
rm -rf skills/kdesign-validate
rm -rf skills/kdesign-impl-plan

# Remove stale symlinks
rm -f ~/.claude/skills/kdesign-validate
rm -f ~/.claude/skills/kdesign-impl-plan

# Also update codex/copilot if installed
rm -f ~/.codex/skills/kdesign-validate ~/.codex/skills/kdesign-impl-plan
rm -f ~/.copilot/skills/kdesign-validate ~/.copilot/skills/kdesign-impl-plan
ln -sfn /Users/karl/Documents/dev/devops-ai/skills/kplan ~/.codex/skills/kplan 2>/dev/null
ln -sfn /Users/karl/Documents/dev/devops-ai/skills/kplan ~/.copilot/skills/kplan 2>/dev/null
```

**Acceptance Criteria:**
- [ ] `skills/kdesign-validate/` directory deleted
- [ ] `skills/kdesign-impl-plan/` directory deleted
- [ ] No stale symlinks for removed skills in `~/.claude/skills/`
- [ ] `~/.claude/skills/kdesign` still resolves to rewritten skill
- [ ] `~/.claude/skills/kplan` resolves to new skill

---

## Milestone 3 Completion Checklist

- [ ] All tasks complete and committed
- [ ] /kdesign replaces kdesign + kdesign-validate
- [ ] /kplan replaces kdesign-impl-plan
- [ ] Replacements validated BEFORE old skills removed
- [ ] Old skill directories and symlinks removed
- [ ] No residual boilerplate in new skills
