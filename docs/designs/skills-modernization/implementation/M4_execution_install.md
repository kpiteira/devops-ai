---
design: docs/designs/skills-modernization/DESIGN.md
architecture: docs/designs/skills-modernization/ARCHITECTURE.md
---

# Milestone 4: Merge Execution Pipeline + Install

**Goal:** `/kbuild` replaces ktask + kmilestone. `install.sh` updated for new skill names and rules distribution. Full token budget verified.

**Branch:** `impl/skills-modernization`
**Builds on:** M3 (design pipeline done, all merges proven)

**Note:** Old skills (ktask, kmilestone, shared) remain available as fallback until Task 4.2 validates the replacement. Only then does Task 4.3 remove them.

---

## Task 4.1: Create New /kbuild

**File(s):**
- `skills/kbuild/SKILL.md` (create)

**Type:** CODING
**Estimated time:** 2-3 hours

**Description:**
Create /kbuild by merging ktask (467 lines) and kmilestone (404 lines) into a single skill that handles both single-task execution and milestone orchestration in one conversation.

**Implementation Notes:**

**What to preserve (from ktask):**
- Research before coding principle
- "Code samples are structure, not implementation" warning
- Task classification (CODING, RESEARCH, MIXED, VALIDATION)
- Unexpected findings guardrail (brief version: verify before proceeding)
- Context document resolution via frontmatter

**What to preserve (from kmilestone):**
- Milestone completion report format — this is an interface contract used for PR creation:
  - E2E tests performed (test, steps, result)
  - Challenges and solutions
  - Failed tests not due to this work
- Resume behavior (idempotent, reads handoff to find starting point)
- Per-task verification between tasks

**What rules now provide (remove from skill):**
- Config loading boilerplate → `project-config.md` rule
- TDD cycle details → `tdd.md` rule
- Quality gate checklist → `quality-gates.md` rule
- Handoff document conventions → `handoffs.md` rule
- E2E testing definition → `e2e-testing.md` rule

**What to remove entirely:**
- "The One Rule" section from kmilestone ("kmilestone invokes ktask") → no longer separate
- E2E agent invocation ceremony (designer/architect/tester) → replaced by rule
- Anti-patterns tables → Opus doesn't need these
- Aggressive language throughout
- Quick reference tables → Opus doesn't need cheat sheets
- Example execution from kmilestone → Opus can figure out the flow
- shared/e2e-prompt.md references → absorbed into rule

**Structure of new skill:**
```
Frontmatter (name, description)
Purpose: execute tasks (TDD) and orchestrate milestones
Modes:
  - Single task: given a task, run research → TDD → verify → handoff
  - Milestone: given a milestone file, sequence tasks with verification between them
Research first: read context docs, find patterns, check handoffs before writing code
Code samples are structure: plan code shows patterns, you implement functionality
Task types: CODING (TDD), RESEARCH (no TDD), MIXED, VALIDATION (E2E against running system)
Milestone completion report: (format specification — interface contract)
Resume: read handoff file to find where to start
```

**Before:** 467 + 404 = 871 lines (2 skills)
**Target:** ~200 lines (1 skill)

**Acceptance Criteria:**
- [ ] Single SKILL.md handles both task and milestone modes
- [ ] No prescribed step numbers or mandatory pauses
- [ ] Research-first principle preserved
- [ ] "Code samples are structure" warning preserved
- [ ] Milestone completion report format preserved (interface contract)
- [ ] Resume behavior described
- [ ] Config/TDD/quality/handoff/E2E details absent (rules provide them)
- [ ] No E2E agent ceremony references
- [ ] ~200 lines (±30)

---

## Task 4.2: Validate Execution Pipeline

**Type:** VALIDATION
**Estimated time:** 1-2 hours

**Description:**
Verify /kbuild is discoverable and functional. Dogfood /kbuild on a real task to validate the TDD flow, handoff output, and quality gates work correctly. Old skills (ktask, kmilestone, shared) still exist as fallback — this validation proves the replacement works before we remove them in Task 4.3.

**Implementation Notes:**

Create the /kbuild symlink now so it's discoverable:
```bash
ln -sfn /Users/karl/Documents/dev/devops-ai/skills/kbuild ~/.claude/skills/kbuild
```

**Verification Steps:**

1. **Structural checks:**
   ```bash
   # New skill exists
   ls skills/kbuild/SKILL.md

   # Line count
   wc -l skills/kbuild/SKILL.md   # Target: ~200

   # No residual boilerplate
   grep -c "Inspect the project root.*for project type indicators" skills/kbuild/SKILL.md
   # Should be 0

   # No E2E agent ceremony
   grep -c "e2e-test-designer\|e2e-test-architect\|e2e-tester" skills/kbuild/SKILL.md
   # Should be 0
   ```

2. **Dogfood /kbuild on a real task:**
   - Pick a real CODING task from a project with a pending implementation plan (ideally a small task — 1-2 hours)
   - Start a fresh conversation, invoke `/kbuild` with the task
   - Evaluate the full cycle: Does it research before coding? Does it follow TDD (RED→GREEN→REFACTOR)? Does it run quality gates? Does it produce a useful handoff?
   - If the skill misses important steps, provides confusing guidance, or produces poor output, fix it before proceeding to Task 4.3
   - Note: We're validating the skill's guidance, not the task's implementation quality

3. **Verify milestone mode:**
   - Invoke `/kbuild` and verify it describes both single-task and milestone modes
   - Verify milestone completion report format is present (interface contract for PR creation)

**Acceptance Criteria:**
- [ ] /kbuild discoverable and loadable
- [ ] Describes both task and milestone modes
- [ ] Milestone completion report format present
- [ ] /kbuild dogfooded on a real task — guided a productive TDD session
- [ ] Old skills still exist (not yet removed — fallback available)

---

## Task 4.3: Remove Old Skills + Update Symlinks

**File(s):**
- `skills/ktask/` (delete directory)
- `skills/kmilestone/` (delete directory)
- `skills/shared/` (delete directory)
- `~/.claude/skills/ktask` (remove symlink)
- `~/.claude/skills/kmilestone` (remove symlink)
- `~/.claude/skills/shared` (remove symlink)

**Type:** CODING
**Estimated time:** 10 min

**Description:**
Now that Task 4.2 has validated /kbuild works, remove the old skill directories and stale symlinks.

**Implementation Notes:**

```bash
# Remove old skill directories
rm -rf skills/ktask
rm -rf skills/kmilestone
rm -rf skills/shared

# Remove stale symlinks
rm -f ~/.claude/skills/ktask
rm -f ~/.claude/skills/kmilestone
rm -f ~/.claude/skills/shared

# Also update codex/copilot if installed
for tool in codex copilot; do
    rm -f ~/.$tool/skills/ktask ~/.$tool/skills/kmilestone ~/.$tool/skills/shared
    ln -sfn /Users/karl/Documents/dev/devops-ai/skills/kbuild ~/.$tool/skills/kbuild 2>/dev/null
done
```

**Acceptance Criteria:**
- [ ] `skills/ktask/`, `skills/kmilestone/`, `skills/shared/` directories deleted
- [ ] No stale symlinks for removed skills
- [ ] Only active skills remain: kdesign, kplan, kbuild, kreview, kissue, kworktree, kinfra-onboard (7)

---

## Task 4.4: Update install.sh + Final Validation

**File(s):**
- `install.sh` (modify)

**Type:** CODING
**Estimated time:** 1 hour

**Description:**
Update install.sh to clean stale symlinks from previous installs and add rules distribution to target projects. Then run comprehensive final validation.

**Implementation Notes:**

The existing `install_skills()` function iterates over `skills/*/` and symlinks each. Since we've renamed/removed directories, the function naturally picks up the right set. But stale symlinks from previous installs on other machines (or after `git pull`) will remain.

Changes needed:

1. **Add stale symlink cleanup** before installing skills:
   ```bash
   cleanup_stale_symlinks() {
       local target_dir="$1"
       for link in "$target_dir"/*/; do
           [ -L "${link%/}" ] || continue
           if [ ! -e "${link%/}" ]; then
               echo "  CLEAN: $(basename "${link%/}") (stale symlink)"
               rm -f "${link%/}"
           fi
       done
   }
   ```

2. **Add rules installation** function:
   ```bash
   install_rules() {
       local project_dir="$1"
       local rules_source="$SCRIPT_DIR/rules"
       local rules_target="$project_dir/.claude/rules"
       [ -d "$rules_source" ] || return 0
       mkdir -p "$rules_target"
       local count=0
       for rule in "$rules_source"/*.md; do
           [ -f "$rule" ] || continue
           local name=$(basename "$rule")
           ln -sfn "$rule" "$rules_target/$name"
           count=$((count + 1))
       done
       echo "  → $count rules installed to $rules_target"
   }
   ```

3. **Add `--rules <project-path>` flag** for installing rules into another project:
   ```bash
   # Usage: ./install.sh --rules /path/to/project
   ```

4. **Self-install rules** for devops-ai itself during regular install.

**Final Validation (after install.sh changes):**

1. **Full inventory check:**
   ```bash
   # Skills directory (7 skills)
   ls -d skills/*/
   # Expected: kbuild, kdesign, kinfra-onboard, kissue, kplan, kreview, kworktree

   # Rules directory (6 rules)
   ls rules/*.md
   # Expected: e2e-testing.md, handoffs.md, project-config.md, quality-gates.md, tdd.md, vertical-slicing.md

   # Symlinks (7 skill + 6 rule)
   ls -la ~/.claude/skills/
   ls -la .claude/rules/
   ```

2. **Token budget verification:**
   ```bash
   echo "=== Skills ==="
   wc -l skills/*/SKILL.md skills/kplan/kplan-categories.md
   echo "=== Rules ==="
   wc -l rules/*.md
   echo "=== Total ==="
   cat skills/*/SKILL.md skills/kplan/kplan-categories.md rules/*.md | wc -l
   ```

   Expected totals:
   | Component | Target lines |
   |-----------|-------------|
   | kdesign | ~200 |
   | kplan + ref | ~350 |
   | kbuild | ~200 |
   | kreview | ~150 |
   | kissue | ~120 |
   | kworktree | ~175 |
   | kinfra-onboard | ~300 |
   | 6 rules | ~170 |
   | **Total** | **~1,665** |

   Before: 4,194 lines. Target: ~1,665 lines. Savings: ~60%.

3. **No residual boilerplate:**
   ```bash
   # Config boilerplate should not appear in any skill except kworktree (unchanged) and kinfra-onboard (light trim)
   grep -rl "Inspect the project root.*for project type indicators" skills/
   # Should return nothing

   # E2E agent ceremony should not appear
   grep -rl "e2e-test-designer\|e2e-test-architect\|e2e-tester" skills/
   # Should return nothing

   # Old skill references should not appear
   grep -rl "kdesign-validate\|kdesign-impl-plan\|/ktask\|/kmilestone" skills/
   # Should return nothing
   ```

4. **Install script test:**
   ```bash
   bash -n install.sh  # Syntax check
   ./install.sh --target claude  # Full install
   ```

5. **Functional smoke test:**
   - Start fresh conversation in devops-ai project
   - Verify rules are loaded (ask "what rules are in context?")
   - Invoke `/kbuild` — verify discoverable
   - Invoke `/kdesign` — verify discoverable

**Acceptance Criteria:**
- [ ] install.sh cleans stale symlinks
- [ ] install.sh supports `--rules <project-path>`
- [ ] install.sh self-installs rules for devops-ai
- [ ] Script still handles kinfra CLI, --target, --force correctly
- [ ] 7 skill directories, 6 rule files
- [ ] Total lines < 1,800 (at least 55% reduction from 4,194)
- [ ] No residual config boilerplate in modernized skills
- [ ] No E2E agent ceremony references
- [ ] No references to removed skill names
- [ ] At least one modernized skill functionally verified in fresh conversation

---

## Milestone 4 Completion Checklist

- [ ] All tasks complete and committed
- [ ] /kbuild replaces ktask + kmilestone
- [ ] Replacements validated BEFORE old skills removed
- [ ] Old skill directories and symlinks removed
- [ ] install.sh updated with cleanup + rules support
- [ ] Total token budget target met
- [ ] Full modernization complete — ready for PR
