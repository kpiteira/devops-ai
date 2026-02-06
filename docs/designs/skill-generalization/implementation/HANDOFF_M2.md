# M2 Handoff

## Task 2.1 Complete: Generalize kdesign

**Approach:** kdesign was nearly 100% universal. Changes were minimal:
- Added YAML frontmatter + Configuration Loading preamble
- "Karl" → "You" (tool-agnostic)
- Output Files section references "configured design path" instead of hardcoded `docs/designs/`
- `docs/designs/` appears only as a default/example, never as a hard requirement

**Size:** 456 lines (under 500-line guidance). No need for `references/` split.

**Pattern established for remaining skills:**
- Configuration Loading is always the first section after the title
- Config preamble lists exactly which config values the skill uses
- No-config fallback asks only the questions this skill needs (kdesign: design path + project name)
- Conversation patterns and pause points preserved exactly from originals

## Task 2.2 Complete: Generalize kdesign-validate

**Changes from original:**
- Removed all "Karl" references → "You" / "User"
- Removed ktrdr command examples (`ktrdr agent trigger`, `ktrdr agent status`) → generic placeholders
- Removed "M1 persistence bug" / checkpoint system example (ktrdr-specific history, lines 600-616)
- Generalized scenario examples (agent sessions → generic entity patterns)
- Interface contract examples now use generic entity names

**Size:** 578 lines. Above 500-line guidance but the validation methodology is the core value and shouldn't be split. The conversation patterns section could move to `references/` if needed later.

## Task 2.3 Complete: Generalize kdesign-impl-plan

**Size:** 974 lines (largest skill). Above 500-line guidance but the planning methodology + appendix tables are the core value. Could move appendix to `references/` later if needed.

**Key changes:**
- All make/docker/psql commands replaced with config-driven references
- Infrastructure sections made conditional ("If infrastructure is configured...")
- E2E sections reference shared prompt
- Specificity checklist examples use generic paths (`src/services/user.py`)
- "M1 persistence bug" anecdote generalized to universal explanation

**Next Task Notes (2.4 — ktask):**
- 431 lines original, moderate ktrdr-specific content
- Main changes: make targets, docker commands, runner fixture pattern
- The runner fixture/ANSI codes section is ktrdr-specific — remove entirely, note in config guidance

## Task 2.4 Complete: Generalize ktask

**Size:** 447 lines (well under 500-line guidance).

**Key changes:**
- Added Configuration Loading preamble (extracts Testing.*, Infrastructure.*, E2E.* from project config)
- All hardcoded `make test-unit`, `make quality`, `docker compose` replaced with "configured command" references
- Infrastructure sections wrapped in "If infrastructure is configured" conditionals
- E2E sections wrapped in "If E2E testing is configured" conditionals
- CLI Test Patterns section (runner fixture, ANSI codes) removed — replaced with generic "Project-Specific Test Patterns" section pointing to `.devops-ai/project.md`
- Config preamble examples kept as illustrations (e.g., `make test-unit`) — these show what config values might look like, not hardcoded commands

**Next Task Notes (2.5 — kmilestone):**
- 354 lines original, nearly 100% universal
- Only ktrdr-specific references are make targets in verification checklist
- Should match ktask invocation syntax from 2.4

## Task 2.5 Complete: Generalize kmilestone

**Size:** 384 lines (well under 500-line guidance). Nearly 100% universal — minimal changes needed.

**Key changes:**
- Added Configuration Loading preamble (extracts Testing.*, E2E.* from project config)
- `make test-unit` / `make quality` in verification checklist → "configured unit test/quality command"
- E2E VALIDATION reminder made conditional on E2E config
- ktrdr-specific example paths replaced with generic feature paths
- Kept validation quality tables (Insufficient vs Valid) with generic examples

**Next Task Notes (2.6 — shared E2E prompt):**
- Extract E2E testing instructions from ktask/kmilestone into shared prompt
- Referenced by both skills via "If E2E is configured, load shared E2E prompt"
- Should contain the agent workflow (designer → architect → tester)

## Task 2.6 Complete: Create Shared E2E Prompt

**Size:** 155 lines. Self-contained E2E testing workflow document.

**What it contains:**
- Three-agent system overview (designer, architect, tester) with roles, models, and when to use each
- Mandatory workflow Steps 1-4 with concrete invocation examples
- Anti-patterns and valid vs invalid validation tables
- Integration guidance for both ktask and kmilestone

**References added:** ktask, kmilestone, and kdesign-impl-plan all reference `skills/shared/e2e-prompt.md` conditionally

**Next Task Notes (2.7 — cross-skill consistency):**
- Verify all 5 skills + shared prompt
- Check config preambles, cross-references, conditional markers, frontmatter
- Grep for any remaining ktrdr-specific content

## Task 2.7 Complete: Cross-Skill Consistency Verification

**All checks passed:**
- Config preambles: identical structure across all 5 skills
- Cross-skill references: match SCENARIOS.md table (kdesign→validate→impl-plan→ktask, kmilestone→ktask)
- Conditional markers: consistent ("If infrastructure is configured", "If E2E testing is configured")
- Zero ktrdr-specific commands (make test, docker compose, psql, ktrdr/) — only examples in config preambles
- Frontmatter: all 5 have name, description, metadata.version in identical format
- ktask invocation: kmilestone uses `/ktask impl: <file> task: <id>`, matches ktask's required params
- All 5 skills reference `.devops-ai/project.md`, none reference `.claude/config`
- Shared E2E prompt referenced by ktask, kmilestone, kdesign-impl-plan
