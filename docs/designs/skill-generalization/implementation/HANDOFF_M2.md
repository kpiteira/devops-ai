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

**Next Task Notes (2.2 — kdesign-validate):**
- Same pattern: frontmatter + config preamble + generalize references
- Watch for ktrdr-specific command examples (`ktrdr agent trigger`, etc.) — replace with generic
- Remove "M1 persistence bug" historical reference
