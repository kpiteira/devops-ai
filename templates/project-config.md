# Project Configuration

This file is read by k* development commands (kdesign, kplan, kbuild, etc.)
to adapt workflows to this project's specific tooling and conventions.

## Project

- **Name:** [project name]
- **Language:** [Python / TypeScript / Go / etc.]
- **Runner:** [uv / npm / go / etc.] — prefix for running commands

## Testing

- **Unit tests:** [command, e.g., "uv run pytest tests/unit"]
- **Quality checks:** [command, e.g., "uv run ruff check . && uv run mypy ."]
- **Integration tests:** [command, or "Not configured"]

## Infrastructure

Not configured.

<!-- If your project has infrastructure (Docker, databases, etc.), replace above with:
- **Start:** [command to start services]
- **Stop:** [command to stop services]
- **Logs:** [command to view recent logs]
- **Health check:** [command or URL to verify services are running]
-->

## E2E Testing

Not configured.

<!-- If your project uses E2E testing, replace above with:
- **System:** [agent / manual / framework-name]
- **Test catalog:** [path to test catalog]
-->

## Paths

- **Design documents:** [e.g., "docs/designs/"]
- **Implementation plans:** [e.g., "implementation/" subfolder within design]
- **Handoff files:** [e.g., "Same directory as implementation plans"]

## Project-Specific Patterns

<!-- Add any project-specific conventions that k* commands should follow.
Examples:
- "Always use the runner fixture for CLI tests (strips ANSI codes)"
- "Never kill processes on port 8000 (Docker container)"
- "Use uv run for all Python commands"
-->
