# Agent Skills Standard — Research Findings

**Date:** 2026-02-05
**Purpose:** Answer the 5 open research questions from M1 Task 1.1
**Sources:** agentskills.io/specification, Claude Code docs, Codex CLI docs, Copilot CLI docs

---

## Q1: Token Limits and Skill Size

**Question:** Agent Skills recommends < 5000 tokens. Our skills are 400-900+ lines. Do we need to modularize?

**Findings:**

The spec defines three levels of progressive disclosure:

| Level | What | Budget | When Loaded |
|-------|------|--------|-------------|
| Metadata | `name` + `description` frontmatter | ~100 tokens | Startup (all skills) |
| Instructions | Full SKILL.md body | < 5000 tokens recommended | On activation |
| Resources | scripts/, references/, assets/ | As needed | On demand |

Key constraints:
- **`name`**: Max 64 characters
- **`description`**: Max 1024 characters
- **Body**: < 5000 tokens recommended, < 500 lines guidance
- **Claude Code specific**: 15,000 character budget for all skill descriptions combined across all installed skills

**Impact on our skills:**

Our 5 skills range from ~350 to ~950 lines. The 5000-token / 500-line guidance is a recommendation, not a hard limit. No tool enforces rejection of larger skills.

However, the spec explicitly supports **progressive disclosure** via optional directories:

```
skill-name/
├── SKILL.md              # Core instructions (< 500 lines)
├── references/           # Detailed reference material
│   └── REFERENCE.md
├── scripts/              # Executable code
└── assets/               # Templates, data files
```

**Recommendation:** For M2, write skills as single SKILL.md files. If any skill exceeds ~500 lines after generalization, move detailed reference sections (like task categories appendix, failure modes table) to `references/`. The skill body can then reference them: `See [task categories](references/task-categories.md) for details.`

**Design update needed:** None — our architecture already supports this. The `references/` directory is a natural fit for large skills.

---

## Q2: Claude Code Slash Invocation

**Question:** Does `/kdesign` work from `~/.claude/skills/kdesign/SKILL.md`?

**Findings:**

**Yes, confirmed.** Claude Code fully supports skill discovery from `~/.claude/skills/`:

- The `name` field in YAML frontmatter becomes the slash command automatically
- `~/.claude/skills/kdesign/SKILL.md` with `name: kdesign` → `/kdesign` works
- `~/.claude/commands/` also works (legacy path) but `skills/` is the recommended standard path
- Skills can also be placed in project-local `.claude/skills/` directories

**Impact:** Our design is correct. We install to `~/.claude/skills/` only, no need for `commands/` dual-install.

**Design update needed:** None — already aligned.

---

## Q3: Codex and Copilot Skill Paths

**Question:** What are the exact skill discovery paths for Codex CLI and Copilot CLI?

**Findings:**

| Tool | Personal Skills Path | Project Skills Path | Notes |
|------|---------------------|--------------------|----|
| Claude Code | `~/.claude/skills/<name>/SKILL.md` | `.claude/skills/<name>/SKILL.md` | Also supports legacy `commands/` |
| Codex CLI | `~/.codex/skills/<name>/SKILL.md` | `.codex/skills/<name>/SKILL.md` | |
| Copilot CLI | `~/.copilot/skills/<name>/SKILL.md` | `.copilot/skills/<name>/SKILL.md` | Also reads `~/.claude/skills/` for cross-compat |
| Gemini CLI | `~/.gemini/skills/<name>/SKILL.md` | `.gemini/skills/<name>/SKILL.md` | Confirmed on agentskills.io |
| Cursor | `~/.cursor/skills/<name>/SKILL.md` | `.cursor/skills/<name>/SKILL.md` | Confirmed on agentskills.io |

**Additional tools confirmed on agentskills.io:** Amp, Goose, VS Code (Agent mode), Aider, Windsurf, Cline, Roo Code — all follow the same `~/.<tool>/skills/` pattern.

**Codex-specific constraints:**
- `name`: Max 100 characters (more lenient than spec's 64)
- `description`: Max 500 characters (more restrictive than spec's 1024)

**Impact:** Our install script should target Claude Code, Codex, and Copilot as primary targets. The pattern is consistent: `~/.<tool>/skills/<name>/`. Our install script's `--target` flag approach is correct.

**Design update needed:** None — already aligned. Codex/Copilot paths confirmed as assumed.

---

## Q4: Frontmatter Fields

**Question:** What YAML frontmatter fields does the standard define? Which are required vs optional?

**Findings:**

| Field | Required | Constraints |
|-------|----------|-------------|
| `name` | **Yes** | Max 64 chars. Lowercase `a-z`, digits, hyphens only. Must match parent directory name. No leading/trailing/consecutive hyphens. |
| `description` | **Yes** | Max 1024 chars. Non-empty. Should describe what + when. |
| `license` | No | License name or reference to bundled file |
| `compatibility` | No | Max 500 chars. Environment requirements |
| `metadata` | No | Arbitrary key-value map (string → string) |
| `allowed-tools` | No | Space-delimited tool list. Experimental. |

**Critical constraint — name format:**

```
✅ kdesign              → valid
✅ kdesign-validate     → valid
✅ kdesign-impl-plan    → valid
✅ ktask                → valid
✅ kmilestone           → valid
```

All 5 of our skill names are valid under the spec. Lowercase, hyphens where needed, no violations.

**Impact:** Our frontmatter from M1 stubs used `version: 0.1.0` — this is not a standard field. It should move to `metadata.version` per spec.

**Design update needed:** Update M1 Task 1.5 and M2 tasks to use `metadata.version` instead of top-level `version`.

---

## Q5: Invocation Syntax Across Tools

**Question:** How do different tools invoke skills? Is `/kdesign args` universal?

**Findings:**

Invocation varies by tool:

| Tool | Invocation | Arguments |
|------|-----------|-----------|
| Claude Code | `/kdesign <args>` | Free text after command name |
| Codex CLI | `/kdesign <args>` | Free text after command name |
| Copilot CLI | `/kdesign <args>` | Free text after command name |

The slash-command invocation pattern is consistent across all three primary targets. The `name` field in frontmatter determines the command name.

**Impact:** Our `/kdesign`, `/ktask` etc. invocations are portable across tools.

**Design update needed:** None.

---

## Summary of Design Impacts

| Finding | Impact | Action |
|---------|--------|--------|
| 5000-token body recommendation | Our large skills may exceed this | Use `references/` for overflow content in M2 |
| `~/.claude/skills/` confirmed | Design already correct | None |
| All tool paths confirmed | Install script design correct | None |
| `name` must match directory | Already planned this way | None |
| `version` not a standard field | Minor frontmatter adjustment | Move to `metadata.version` |
| `description` max 1024 chars | Our descriptions are short, fine | None |
| Progressive disclosure supported | Natural fit for large skills | Leverage in M2 if needed |

**Overall:** No design contradictions found. One minor adjustment (version field placement). The Agent Skills standard is well-aligned with our architecture.

---

## Broader Ecosystem Notes

The Agent Skills standard has significantly broader adoption than initially expected. Beyond our three targets (Claude Code, Codex, Copilot), it's adopted by:

- Gemini CLI (Google)
- Cursor
- Amp
- Goose (Block)
- VS Code Agent mode
- Aider
- Windsurf (Codeium)
- Cline
- Roo Code

This validates the decision to build on this standard — skills we write will be usable across a wide ecosystem, not just the three tools we're targeting initially.

A validation CLI exists: `skills-ref validate ./my-skill` (from `agentskills/agentskills` on GitHub). We could add this to our install script or CI in a future milestone.
