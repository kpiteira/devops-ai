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

**Next Task Notes (1.2 — Config Template):**
- Template goes in `templates/project-config.md`
- Config path is `.devops-ai/project.md` (tool-agnostic)
- Sections: Project, Testing, Infrastructure, E2E, Paths, Project-Specific Patterns
- Optional sections default to "Not configured"
