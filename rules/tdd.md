# Test-Driven Development

All coding tasks follow the TDD cycle: RED, GREEN, REFACTOR.

## RED — Write failing tests first

Before any implementation, write tests covering happy path, error cases, and edge cases. Run them to confirm they fail meaningfully (not due to import errors or missing files). If you catch yourself writing implementation before tests, stop and go back to this phase.

## GREEN — Minimal implementation

Write just enough code to make tests pass. Follow existing patterns in the codebase. Run tests frequently. Don't add untested features.

## REFACTOR — Improve quality

Clean up code, extract patterns, add type hints. Run tests after each change to confirm nothing breaks. Run quality checks if configured.

## Why TDD matters

Tests written after implementation tend to test what the code does, not what it should do. Writing tests first forces you to think about behavior and edge cases before committing to an implementation approach.
