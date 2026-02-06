# M1 Handoff

## Task 1.1 Complete: Research Agent Skills Standard Compatibility

**Key findings for subsequent tasks:**

- **Frontmatter**: `version` is NOT a standard field. Use `metadata.version: "0.1.0"` instead. Updated all design docs and milestone files.
- **Name constraints**: Lowercase only, max 64 chars, must match directory name, no leading/trailing/consecutive hyphens. All 5 of our names pass.
- **Description**: Max 1024 chars (Codex is more restrictive: max 500 chars). Keep descriptions short.
- **Size guidance**: < 500 lines / < 5000 tokens is recommended, not enforced. Use `references/` directory for overflow — the spec explicitly supports this.
- **Install paths confirmed**: `~/.claude/skills/`, `~/.codex/skills/`, `~/.copilot/skills/`. Copilot also reads `~/.claude/skills/` for cross-compat.
- **Slash invocation confirmed**: `name` field → slash command automatically in Claude Code, Codex, Copilot.
- **Broader adoption**: 10+ tools support Agent Skills (Gemini CLI, Cursor, Amp, Goose, VS Code, Aider, Windsurf, Cline, Roo Code).
- **Validation CLI exists**: `skills-ref validate ./my-skill` — consider adding to install script or CI later.

## Tasks 1.2-1.5 Complete: Templates, Install Script, Skill Stubs

**What was created:**
- `templates/project-config.md` — 51 lines, all 6 sections, optional sections use "Not configured" with HTML comments showing the full format
- `templates/AGENTS.md.template` — Tool-agnostic (says "The AI" not "Claude"), includes `.devops-ai/project.md` reference
- `install.sh` — Symlink installer with `--force` and `--target` flags. Tested: idempotent, SKIP for non-symlink conflicts, force overwrite works
- 5 stub SKILL.md files — Valid frontmatter with `metadata.version` (not top-level `version`)

**E2E validation passed:**
- 5 symlinks created in `~/.claude/skills/`
- All resolve to `devops-ai/skills/<name>/`
- Template copies correctly with all sections
- `--force` and idempotency verified

**Next Milestone Notes (M2 — All Five Skills):**
- Stub SKILL.md files will be replaced with full generalized content
- Watch for skill size — if any exceeds ~500 lines, use `references/` directory
- All skill names pass Agent Skills naming validation
- Descriptions should stay under 500 chars (Codex constraint)
