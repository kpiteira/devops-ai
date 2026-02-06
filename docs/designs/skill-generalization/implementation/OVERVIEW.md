# Skill Generalization: Implementation Plan

## Milestone Summary

| # | Name | Tasks | E2E Test | Status |
|---|------|-------|----------|--------|
| M1 | Foundation + Agent Skills Research | 5 | Install script creates valid symlinks, templates copy correctly | - |
| M2 | All Five Skills | 7 | Skills load config, no hardcoded ktrdr references remain | - |
| M3 | Graceful Degradation | 4 | Skills work without config, offer to create one | - |
| M4 | Documentation + Polish | 3 | Fresh clone + README instructions = working setup | - |

**Total Tasks:** 19

## Dependency Graph

```
M1 (Foundation) → M2 (All Skills) → M3 (Degradation) → M4 (Docs)
```

Strict linear chain. Each milestone depends on the previous.

## Architecture Alignment

### Core Patterns

| Pattern | Implementation Approach |
|---------|------------------------|
| Skills as Prompts | Each SKILL.md is self-contained markdown with YAML frontmatter |
| Config as Prompt | `.devops-ai/project.md` — natural language, no parsing |
| Symlink Distribution | `install.sh` creates directory symlinks to `~/.<tool>/skills/` |
| Self-Contained Skills | Each skill has its own config loading preamble (~10-15 lines) |
| Conditional Sections | "If infrastructure configured..." — Claude skips when not applicable |
| Agent Skills Standard | Directory-based: `skills/<name>/SKILL.md` with YAML frontmatter |

### What We Will NOT Do

- No code, runtime, or framework
- No programmatic config parsing
- No shared includes between skills
- No ktrdr migration (deferred)
- No custom format per tool

## Reference Documents

- Design: [DESIGN.md](../DESIGN.md)
- Architecture: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Validation: [SCENARIOS.md](../SCENARIOS.md)
