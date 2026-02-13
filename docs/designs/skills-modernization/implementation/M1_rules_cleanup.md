---
design: docs/designs/skills-modernization/DESIGN.md
architecture: docs/designs/skills-modernization/ARCHITECTURE.md
---

# Milestone 1: Rules + Cleanup

**Goal:** Shared principles auto-load into every conversation via `.claude/rules/`. Old SDD agents removed.

**Branch:** `impl/skills-modernization`

**Why M1:** Everything else depends on rules existing. This is additive and risk-free — existing skills continue working (they still have inline boilerplate, which we remove in M2+).

---

## Task 1.1: Create 6 Rule Files

**File(s):**
- `rules/project-config.md` (create)
- `rules/tdd.md` (create)
- `rules/quality-gates.md` (create)
- `rules/handoffs.md` (create)
- `rules/vertical-slicing.md` (create)
- `rules/e2e-testing.md` (create)

**Type:** CODING
**Estimated time:** 2-3 hours

**Description:**
Extract shared principles from existing skills into 6 focused rule files. Each rule distills the duplicated content from multiple skills into a concise, principled statement.

**Implementation Notes:**

For each rule, the process is: read the relevant sections from existing skills, identify the core principle, distill into concise rule text. The tone should be principled (Opus-era), not prescriptive (Sonnet-era).

**Source material for each rule:**

| Rule | Extract from | Key sections |
|------|-------------|--------------|
| `project-config.md` | kdesign:16-46, ktask:16-53, kmilestone:16-49, kissue:12-29, kreview:27-34 | Config loading + fallback + generation offer |
| `tdd.md` | ktask:199-235, kissue:124-148 | RED→GREEN→REFACTOR cycle |
| `quality-gates.md` | ktask:349-359, kmilestone:152-159 | Test/quality/commit checklist |
| `handoffs.md` | ktask:365-398 | Handoff document conventions |
| `vertical-slicing.md` | kdesign-validate:361-430 | Vertical milestone principles |
| `e2e-testing.md` | shared/e2e-prompt.md (entire file), ktask:265-331, kmilestone:112-148 | Real E2E definition + structural enforcement |

**Token targets per rule:**

| Rule | Target tokens | Target lines |
|------|--------------|--------------|
| `project-config.md` | ~250 | 30-40 |
| `tdd.md` | ~200 | 20-30 |
| `quality-gates.md` | ~200 | 20-30 |
| `handoffs.md` | ~200 | 20-30 |
| `vertical-slicing.md` | ~200 | 20-30 |
| `e2e-testing.md` | ~400 | 40-60 |
| **Total** | **~1,450** | **~170** |

**Language guidelines:**
- No "CRITICAL", "MANDATORY", "MUST", "NEVER" — use normal language
- State what to do, not what not to do
- Include the "why" briefly — Opus uses reasoning to apply principles
- No prescribed pauses or output templates

**Acceptance Criteria:**
- [ ] 6 rule files created in `rules/` directory
- [ ] Each rule is self-contained (understandable without reading skills)
- [ ] No prescribed step numbers or output templates
- [ ] Total tokens ~1,500 (verify with rough count)
- [ ] project-config.md covers: load config, fallback behavior, generation offer
- [ ] tdd.md covers: RED→GREEN→REFACTOR, test-first discipline
- [ ] quality-gates.md covers: tests, quality checks, commits, no security vulnerabilities
- [ ] handoffs.md covers: when/what/where for handoff docs, what to exclude
- [ ] vertical-slicing.md covers: E2E-testable milestones, vertical not horizontal
- [ ] e2e-testing.md covers: definition of real E2E, structural requirement, evidence, test catalog

---

## Task 1.2: Wire Rules into Project + Remove Old Agents

**File(s):**
- `.claude/rules/` (create directory + symlinks)
- `~/.claude/agents/` (remove 9 old files)

**Type:** CODING
**Estimated time:** 30 min

**Description:**
Set up `.claude/rules/` in the devops-ai project so rules auto-load during development. Remove 9 old SDD-era agents from `~/.claude/agents/` that are unused and could confuse Opus.

**Implementation Notes:**

For rules wiring, symlink each rule file from `rules/` to `.claude/rules/`:
```bash
mkdir -p .claude/rules
ln -sfn ../../rules/project-config.md .claude/rules/project-config.md
# ... for each rule
```

Symlinks (not copies) so `git pull` updates rules. The `.claude/rules/` symlinks should be gitignored since they point to repo-relative paths.

For agent cleanup, remove these files from `~/.claude/agents/`:
- `architecture-specialist.md`
- `bundler-specialist.md`
- `coder-specialist.md`
- `milestone-planning-specialist.md`
- `project_structure_analysis.md`
- `requirements-specialist.md`
- `roadmap-specialist.md`
- `task-blueprint-specialist.md`
- `validator-specialist.md`

**Acceptance Criteria:**
- [ ] `.claude/rules/` directory exists with 6 symlinks
- [ ] Each symlink resolves correctly (`readlink` shows path to `rules/*.md`)
- [ ] `.gitignore` updated to exclude `.claude/rules/` symlinks (or the symlinks are committed if preferred)
- [ ] 9 old SDD agents removed from `~/.claude/agents/`
- [ ] `~/.claude/agents/` is empty (or contains only intentional agents)

---

## Task 1.3: Validate Rules + Cleanup

**Type:** VALIDATION
**Estimated time:** 15 min

**Description:**
Verify that rules auto-load in a fresh conversation and old agents are gone.

**Verification Steps:**

1. **Rules auto-load check:**
   - Start a new Claude Code conversation in the devops-ai project
   - Ask: "What rules are loaded in this conversation?"
   - Verify all 6 rules appear in context

2. **Structural checks:**
   ```bash
   # All 6 rule files exist
   ls rules/*.md | wc -l  # Should be 6

   # All symlinks resolve
   for f in .claude/rules/*.md; do readlink "$f" && echo "OK: $f"; done

   # Old agents gone
   ls ~/.claude/agents/*.md 2>/dev/null | wc -l  # Should be 0

   # Token count (rough: wc -w as proxy, ~0.75 tokens/word)
   wc -w rules/*.md
   ```

3. **No regression check:**
   - Existing skills still load and are invocable (they still have inline boilerplate — removing it is M2)

**Acceptance Criteria:**
- [ ] All 6 rules auto-load in fresh conversation
- [ ] All symlinks resolve correctly
- [ ] `~/.claude/agents/` contains no old SDD agents
- [ ] Total rule word count < 1,200 words (~1,500 tokens)
- [ ] Existing skills still work (invoke one, e.g., `/kreview`)

---

## Milestone 1 Completion Checklist

- [ ] All tasks complete and committed
- [ ] 6 rule files in `rules/` directory
- [ ] `.claude/rules/` wired up
- [ ] Old SDD agents removed
- [ ] No regressions in existing skills
