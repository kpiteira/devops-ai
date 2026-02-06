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
