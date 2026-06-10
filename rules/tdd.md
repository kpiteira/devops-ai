# Test-Driven Development

All coding tasks follow the TDD cycle: RED, GREEN, REFACTOR.

## RED — Write failing tests first

Before any implementation, write tests covering happy path, error cases, and edge cases. Run them to confirm they fail meaningfully (not due to import errors or missing files). If you catch yourself writing implementation before tests, stop and go back to this phase.

## GREEN — Minimal implementation

Write just enough code to make tests pass. Follow existing patterns in the codebase. Run tests frequently. Don't add untested features.

## REFACTOR — Improve quality

Clean up code, extract patterns, add type hints. Run tests after each change to confirm nothing breaks. Run quality checks if configured.

## What a unit is: behavior at the process boundary

A unit is a behavior, not a class. Write tests through the smallest *stable* public surface — a service function, an engine entry point, the in-process API (an ASGI test client makes no network calls) — and let everything inside the process run real. Speed comes from avoiding I/O, not from avoiding your own code: calling your own functions costs nanoseconds, and the <100ms budget survives running the entire domain layer.

Replace only what is slow or non-deterministic — network, database, subprocess, LLM calls, the clock — and prefer **hand-written fakes implementing a port** (in-memory repository, fixed clock, canned responses) over `patch()`. A patch is welded to an import path and a call signature, so it breaks when structure changes even though behavior didn't; a fake survives any refactor that preserves the contract. Patching first-party code is a coupling smell the structural gates count (see the `structural-gates` rule). Integration tests then have one precise job: prove each fake honest by running the same contract suite against the real adapter.

Assert observable outcomes, not call choreography. "The service called `repo.save(x)`" fails on restructuring with behavior intact — a corrupted signal that teaches the build loop to distrust red. Assert an interaction only when the interaction *is* the contract ("exactly one notification sent"). The bar for every test: **it fails if and only if behavior the design cares about changed.**

## Why TDD matters

Tests written after implementation tend to test what the code does, not what it should do. Writing tests first forces you to think about behavior and edge cases before committing to an implementation approach.
