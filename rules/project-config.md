# Project Configuration

Every project using devops-ai skills stores configuration at `.devops-ai/project.md`. Load this file at the start of any skill workflow.

## What to extract

- **Project.name** — project identifier
- **Testing.unit_tests** — command to run unit tests (e.g., `uv run pytest tests/unit`)
- **Testing.quality_checks** — command to run quality/lint checks (e.g., `uv run ruff check src/`)
- **Infrastructure.start** — command to start infrastructure (if configured)
- **Infrastructure.logs** — command to check logs (if configured)
- **E2E.enabled** — whether E2E testing is configured
- **Paths.design_documents** — where design docs live

## Handling missing config

If the file exists but values are missing:
- Essential values (Testing.*): ask for them
- Optional values (Infrastructure, E2E): skip silently, note what was skipped

If the file does not exist:
- Ask for test command and quality command
- Offer to create `.devops-ai/project.md` from the template at `templates/project-config.md`

## Auto-detecting project type

When generating config, inspect the project root:
- `pyproject.toml` → Python (extract name, look for pytest/ruff config)
- `package.json` → Node/TypeScript (extract name, scripts.test, scripts.lint)
- `Makefile` → look for test/quality/lint targets
- `go.mod` → Go (extract module name)
- `Cargo.toml` → Rust (extract package name)

Pre-fill values from what you find, show the draft, and let the user confirm before writing.
