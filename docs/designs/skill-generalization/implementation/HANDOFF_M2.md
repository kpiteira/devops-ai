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

**Next Task Notes (2.3 — kdesign-impl-plan):**
- This is the LARGEST skill (944 lines original). Will likely exceed 500 lines.
- Most ktrdr-specific content: make targets, docker commands, psql queries, ktrdr/ paths
- Task categories appendix and failure modes table are universal — preserve
- May need `references/` split for appendix material
