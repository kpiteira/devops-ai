---
design: docs/designs/skill-generalization/DESIGN.md
architecture: docs/designs/skill-generalization/ARCHITECTURE.md
---

# Milestone 2: All Five Skills

**Branch:** `feature/devops-ai-M2-skills`
**Project Root:** `~/Documents/dev/devops-ai/`
**Goal:** All k* commands work in a configured project — generalized from ktrdr originals to portable, configuration-driven skills.

> **All file paths in this plan are relative to the devops-ai repo.**
> This plan is executed from ktrdr (which has the k* commands) but all
> files are created and modified in `~/Documents/dev/devops-ai/`.

**Builds on:** M1 (install mechanism, templates, Agent Skills format confirmed)

---

## E2E Validation

### Test Scenario

```bash
# 1. Verify all skills have valid frontmatter
for skill in skills/*/SKILL.md; do
  head -1 "$skill" | grep -q "^---" && echo "OK: $skill" || echo "FAIL: $skill"
done

# 2. Verify config loading preamble in every skill
grep -l "Configuration Loading" skills/*/SKILL.md | wc -l  # should be 5

# 3. Verify NO ktrdr-specific hardcoded commands remain
# These should return zero matches:
grep -r "make test-unit\|make quality\|make test" skills/
grep -r "docker compose" skills/
grep -r "psql " skills/
grep -r "ktrdr/" skills/

# 4. Verify conditional sections exist where needed
grep -l "infrastructure configured\|infrastructure is configured" skills/ktask/SKILL.md
grep -l "infrastructure configured\|infrastructure is configured" skills/kmilestone/SKILL.md
grep -l "e2e configured\|E2E.*configured\|e2e is configured" skills/ktask/SKILL.md
grep -l "e2e configured\|E2E.*configured\|e2e is configured" skills/kmilestone/SKILL.md

# 5. Verify E2E prompt file exists
test -f skills/shared/e2e-prompt.md && echo "OK" || echo "MISSING"

# 6. Verify all skills reference .devops-ai/project.md (not .claude/config/)
grep -r "\.devops-ai/project\.md" skills/*/SKILL.md | wc -l  # should be 5
grep -r "\.claude/config" skills/  # should return nothing
```

**Success Criteria:**
- [ ] All 5 SKILL.md files have valid YAML frontmatter
- [ ] All 5 skills have Configuration Loading preamble
- [ ] Zero ktrdr-specific references (`make test-unit`, `docker compose`, `psql`, `ktrdr/`)
- [ ] Conditional infrastructure sections in ktask, kmilestone, kdesign-impl-plan
- [ ] Conditional E2E sections in ktask, kmilestone
- [ ] E2E prompt file exists at `skills/shared/e2e-prompt.md`
- [ ] All skills reference `.devops-ai/project.md`

---

## Task 2.1: Generalize kdesign

**File(s):** `skills/kdesign/SKILL.md` (replace stub from M1)
**Type:** CODING
**Estimated time:** 2 hours
**Architectural Pattern:** Skills as Prompts, Config as Prompt, Self-Contained Skills
**Source:** ktrdr `.claude/commands/kdesign.md` (433 lines)

**Description:**
Generalize kdesign from the ktrdr original. This is the simplest skill to generalize — nearly 100% universal content. It validates the generalization pattern before tackling more complex skills.

**What to change from ktrdr original:**
1. Add YAML frontmatter (`name: kdesign`, `description`, `version: 0.1.0`)
2. Add Configuration Loading preamble as first section after the title
3. Replace hardcoded `docs/designs/` path with reference to configured design path
4. Remove any ktrdr-specific examples (minimal — mostly generic already)

**Config values used:** `Paths.design_documents`, `Project.name`

**Implementation Notes:**
- Read the ktrdr original at `.claude/commands/kdesign.md` first
- The design workflow, conversation patterns, and document structure are preserved exactly
- Only the config loading preamble and path references change
- The preamble should reference `.devops-ai/project.md` and extract Paths.design_documents

**Acceptance Criteria:**
- [ ] Valid YAML frontmatter with name, description, version
- [ ] Configuration Loading section is the first workflow section
- [ ] References `.devops-ai/project.md` for config
- [ ] No hardcoded paths — uses "configured design documents path"
- [ ] Core design workflow preserved from ktrdr original
- [ ] Conversation patterns and pauses preserved

---

## Task 2.2: Generalize kdesign-validate

**File(s):** `skills/kdesign-validate/SKILL.md` (replace stub)
**Type:** CODING
**Estimated time:** 2 hours
**Architectural Pattern:** Skills as Prompts, Config as Prompt, Self-Contained Skills
**Source:** ktrdr `.claude/commands/kdesign-validate.md` (616 lines)

**Description:**
Generalize kdesign-validate. Small changes needed — the validation methodology is universal. The only ktrdr-specific content is a few command examples used as illustrations.

**What to change from ktrdr original:**
1. Add YAML frontmatter
2. Add Configuration Loading preamble
3. Replace ktrdr-specific command examples (`ktrdr agent trigger`, `ktrdr agent status`) with generic placeholders or config-driven references
4. Remove "M1 persistence bug" historical reference (ktrdr-specific)
5. Replace any hardcoded paths with configured values

**Config values used:** `Paths.design_documents`, `Project.name`

**Implementation Notes:**
- The validation methodology (scenarios, gap analysis, interface contracts, milestone structure) is 100% universal — preserve it exactly
- The ktrdr command examples in scenario traces can be replaced with generic examples or references to "the project's CLI commands"
- The gap analysis categories and conversation patterns are the core value — don't lose them

**Acceptance Criteria:**
- [ ] Valid YAML frontmatter
- [ ] Configuration Loading preamble present
- [ ] No ktrdr-specific command examples
- [ ] No ktrdr project history references
- [ ] Validation methodology fully preserved
- [ ] Gap analysis categories preserved
- [ ] Conversation patterns preserved

---

## Task 2.3: Generalize kdesign-impl-plan

**File(s):** `skills/kdesign-impl-plan/SKILL.md` (replace stub)
**Type:** CODING
**Estimated time:** 3-4 hours
**Architectural Pattern:** Skills as Prompts, Config as Prompt, Conditional Sections
**Source:** ktrdr `.claude/commands/kdesign-impl-plan.md` (944 lines)

**Description:**
Generalize kdesign-impl-plan. This is the largest skill and has the most ktrdr-specific references — make targets, docker compose commands, psql queries, and specific service paths all need to become config-driven.

**What to change from ktrdr original:**
1. Add YAML frontmatter
2. Add Configuration Loading preamble
3. Replace all hardcoded commands:
   - `make test-unit` → "[UNIT_TEST_COMMAND from project config]" or natural language reference
   - `make quality` → "[QUALITY_COMMAND from project config]"
   - `docker compose logs backend --since 5m | grep -i error` → "[INFRA_LOGS_COMMAND from project config]" (conditional on infrastructure)
   - `psql -c "SELECT..."` → generic "verify persistence using project's database tool" (conditional)
4. Replace ktrdr-specific paths:
   - `ktrdr/services/training.py` → generic example path
5. Make infrastructure sections conditional:
   - Smoke test patterns → "If infrastructure is configured in project config"
   - Database verification → "If project uses a database"
6. Make E2E sections conditional and reference the shared E2E prompt

**Config values used:** `Testing.*`, `Infrastructure.*`, `E2E.*`, `Paths.*`

**Implementation Notes:**
- The planning methodology (architecture alignment, capabilities, vertical milestones, task expansion) is 100% universal — preserve exactly
- The task categories appendix (Persistence, Wiring/DI, State Machine, etc.) is universal — preserve
- The failure modes table is universal — preserve
- Only the smoke test patterns and example commands need to become config-driven
- The E2E test agent integration (designer/architect/tester) is universal — preserve
- This is the longest skill. Watch the token budget — if it exceeds Agent Skills limits from Task 1.1 research, discuss modularization

**Acceptance Criteria:**
- [ ] Valid YAML frontmatter
- [ ] Configuration Loading preamble present
- [ ] Zero hardcoded make/docker/psql commands
- [ ] Infrastructure sections clearly conditional
- [ ] E2E sections clearly conditional, reference shared E2E prompt
- [ ] Planning methodology fully preserved
- [ ] Task categories and failure modes preserved
- [ ] Example commands use config references, not hardcoded values

---

## Task 2.4: Generalize ktask

**File(s):** `skills/ktask/SKILL.md` (replace stub)
**Type:** CODING
**Estimated time:** 2-3 hours
**Architectural Pattern:** Skills as Prompts, Config as Prompt, Conditional Sections
**Source:** ktrdr `.claude/commands/ktask.md` (431 lines)

**Description:**
Generalize ktask — the TDD task execution skill. Has moderate ktrdr-specific content: make targets, docker commands, and a CLI test pattern specific to ktrdr.

**What to change from ktrdr original:**
1. Add YAML frontmatter
2. Add Configuration Loading preamble
3. Replace hardcoded commands:
   - `make test-unit` → reference to configured unit test command
   - `make quality` → reference to configured quality command
   - `docker compose up -d` → conditional infrastructure start command
   - `docker compose logs backend` → conditional infrastructure logs command
4. Move CLI test pattern (`runner` fixture, ANSI codes) to "Project-Specific Patterns" guidance — this belongs in each project's `.devops-ai/project.md`, not in the skill
5. Make infrastructure sections conditional
6. Make E2E sections conditional, reference shared E2E prompt

**Config values used:** `Testing.unit_tests`, `Testing.quality_checks`, `Infrastructure.*`, `E2E.*`

**Implementation Notes:**
- The TDD cycle (RED → GREEN → REFACTOR) is 100% universal — preserve exactly
- The handoff document structure is universal — preserve
- The 5-phase workflow (Setup → Research → Implement → Verify → Completion) is universal — preserve
- The E2E agent workflow (mandatory for VALIDATION tasks) is universal — preserve
- The `runner` fixture pattern (line 412 of original) is ktrdr-specific — remove from skill, note that project-specific test patterns belong in config

**Acceptance Criteria:**
- [ ] Valid YAML frontmatter
- [ ] Configuration Loading preamble present
- [ ] Zero hardcoded make/docker commands
- [ ] TDD cycle and 5-phase workflow preserved
- [ ] Handoff document structure preserved
- [ ] Infrastructure sections conditional
- [ ] E2E sections conditional
- [ ] No ktrdr-specific test patterns (runner fixture, ANSI codes)

---

## Task 2.5: Generalize kmilestone

**File(s):** `skills/kmilestone/SKILL.md` (replace stub)
**Type:** CODING
**Estimated time:** 2 hours
**Architectural Pattern:** Skills as Prompts, Config as Prompt, Conditional Sections
**Source:** ktrdr `.claude/commands/kmilestone.md` (354 lines)

**Description:**
Generalize kmilestone — the milestone orchestration skill. Nearly 100% universal content. The only ktrdr-specific references are make targets in the verification checklist.

**What to change from ktrdr original:**
1. Add YAML frontmatter
2. Add Configuration Loading preamble
3. Replace hardcoded commands in verification checklist:
   - `make test-unit` → reference to configured unit test command
   - `make quality` → reference to configured quality command
4. Make E2E sections conditional

**Config values used:** `Testing.unit_tests`, `Testing.quality_checks`, `E2E.*`

**Implementation Notes:**
- The orchestration pattern ("kmilestone invokes ktask, ktask does the work") is universal — preserve exactly
- The idempotent execution pattern (read handoff, resume from first incomplete) is universal — preserve
- The completion output format (3 tables) is universal — preserve
- The `/ktask` invocation syntax should match the generalized ktask from Task 2.4

**Acceptance Criteria:**
- [ ] Valid YAML frontmatter
- [ ] Configuration Loading preamble present
- [ ] Zero hardcoded make commands
- [ ] Orchestration pattern preserved
- [ ] Idempotent execution preserved
- [ ] Completion output format preserved
- [ ] E2E sections conditional
- [ ] `/ktask` invocation syntax matches generalized ktask

---

## Task 2.6: Create Shared E2E Prompt

**File(s):** `skills/shared/e2e-prompt.md` (create)
**Type:** CODING
**Estimated time:** 1-2 hours
**Architectural Pattern:** Conditional Sections

**Description:**
Extract E2E testing instructions into a shared prompt file that ktask and kmilestone load conditionally when E2E is configured in the project.

**What to do:**
Create `skills/shared/e2e-prompt.md` containing:
- E2E test agent workflow (designer → architect → tester)
- When to invoke each agent
- How to interpret results
- Integration with the task/milestone workflow

**Implementation Notes:**
- Content comes from the E2E sections of the ktrdr originals (ktask.md and kmilestone.md)
- The three-agent system (e2e-test-designer, e2e-test-architect, e2e-tester) is universal
- Skills reference this file with: "If E2E testing is configured in project config, also read `skills/shared/e2e-prompt.md` for E2E workflow instructions"
- This file should be self-contained — readable without the parent skill's context

**Acceptance Criteria:**
- [ ] `skills/shared/e2e-prompt.md` exists
- [ ] Contains E2E agent workflow (designer, architect, tester)
- [ ] Self-contained — understandable without parent skill context
- [ ] Referenced by ktask and kmilestone skills (conditional load)

---

## Task 2.7: Verify Cross-Skill Consistency

**File(s):** All 5 `skills/*/SKILL.md` files (review, possibly modify)
**Type:** MIXED
**Estimated time:** 1-2 hours

**Description:**
After all 5 skills are generalized, verify cross-skill consistency: config loading preambles match, cross-skill references are correct, conditional section markers are consistent, and no ktrdr-specific content slipped through.

**What to verify:**
1. All config loading preambles use identical language and reference `.devops-ai/project.md`
2. Cross-skill references match (kdesign → "Run /kdesign-validate", etc.)
3. Conditional section markers use consistent language ("If infrastructure is configured...", "If E2E testing is configured...")
4. No hardcoded ktrdr commands remain (grep for `make test`, `docker compose`, `psql`, `ktrdr/`)
5. YAML frontmatter is consistent (all have name, description, version: 0.1.0)
6. The `/ktask` invocation syntax in kmilestone matches ktask's expected input

**Acceptance Criteria:**
- [ ] Config preambles identical across all 5 skills
- [ ] Cross-skill references correct per SCENARIOS.md table
- [ ] Conditional markers consistent
- [ ] Zero ktrdr-specific commands (verified by grep)
- [ ] Frontmatter consistent
- [ ] ktask invocation syntax consistent between kmilestone and ktask

---

## Milestone 2 Completion Checklist

- [ ] Task 2.1: kdesign generalized
- [ ] Task 2.2: kdesign-validate generalized
- [ ] Task 2.3: kdesign-impl-plan generalized
- [ ] Task 2.4: ktask generalized
- [ ] Task 2.5: kmilestone generalized
- [ ] Task 2.6: Shared E2E prompt created
- [ ] Task 2.7: Cross-skill consistency verified
- [ ] E2E test scenario passes (above)
- [ ] M1 E2E test still passes (install script, templates)
- [ ] All files committed
