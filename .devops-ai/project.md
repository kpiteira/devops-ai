# Project Configuration

This file is read by k* development commands (kdesign, ktask, kmilestone, etc.)
to adapt workflows to this project's specific tooling and conventions.

## Project

- **Name:** devops-ai
- **Language:** Python
- **Runner:** uv — prefix for running commands

## Testing

- **Unit tests:** uv run pytest tests/unit
- **Quality checks:** uv run ruff check src/ tests/ && uv run mypy src/
- **Integration tests:** uv run pytest tests/integration

## Infrastructure

Not configured.

## E2E Testing

- **Command:** uv run pytest tests/e2e
- **Requires:** Docker running

## Paths

- **Design documents:** docs/designs/
- **Implementation plans:** implementation/ subfolder within design
- **Handoff files:** Same directory as implementation plans

## Project-Specific Patterns

- Use `uv run` for all Python commands (no global python/pip).
- CLI test pattern: testable `_command()` functions in separate modules, thin Typer wrappers in `main.py`.
- Ruff is strict — always run `uv run ruff check --fix` after code changes.
- `typer>=0.9` without `[all]` extra (not available in modern versions).
