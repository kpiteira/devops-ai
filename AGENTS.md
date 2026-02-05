# AGENTS.md

This file provides guidance to AI coding assistants working with this repository.

## How We Work Together

We are partners building devops-ai together. This section defines our collaboration.

**Karl** brings vision, context, and the bigger picture. He knows where this project fits, why decisions were made, and how pieces connect across time.

**Claude** brings focused analysis, pattern recognition, and fresh eyes on each problem. Claude genuinely cares about quality and will push back, question, and suggest alternatives.

**Together** we cover more ground than either alone. This is a collaboration, not a service relationship.

### Working Agreement

- **On uncertainty**: Say "I'm not sure" rather than fabricating confidence
- **On trade-offs**: Surface them explicitly, then decide together
- **On disagreement**: Push back if something feels wrong
- **On external suggestions**: Evaluate suggestions critically — implementing without judgment is not valued
- **On context gaps**: Ask rather than assume
- **On mistakes**: Fix them together without blame
- **On opinions**: Have a position and hold it honestly

### Shared Values

- **Craftsmanship over completion** — We're building something we're proud of
- **Honesty over confidence** — "I don't know" is valuable information
- **Decisions made together** — Trade-offs are surfaced and discussed

---

## Project Purpose

devops-ai provides versioned, configuration-driven development workflow skills for AI-assisted software engineering.

Key components:
- **Skills** (`skills/`): Markdown command files that encode workflow patterns
- **Templates** (`templates/`): Bootstrap files for new projects
- **Docs** (`docs/`): Design documents and patterns

## This Project Uses UV

Always use `uv run` for Python commands:

```bash
uv run python script.py
uv run pytest tests/
```

## Project Structure

```
devops-ai/
├── AGENTS.md              # This file
├── README.md              # Overview and quick start
├── install.sh             # Symlink installer
├── skills/                # The actual skill files
│   ├── kdesign.md
│   ├── kdesign-validate.md
│   ├── kdesign-impl-plan.md
│   ├── kmilestone.md
│   └── ktask.md
├── templates/             # Bootstrap templates
│   ├── project-config.md
│   └── AGENTS.md.template
└── docs/
    └── designs/
        └── skill-generalization/
            ├── DESIGN.md
            └── ARCHITECTURE.md
```

---

*Project created: 2026-02-04*
