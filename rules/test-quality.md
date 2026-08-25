# Test Quality

What makes a test honest — for planner-authored acceptance tests (the contract) and
executor-written unit tests (the tools) alike. How anyone sequences their work is not
this rule's business; what a green test is allowed to mean is.

## The bar

A test is honest when **it fails if and only if behavior the design cares about
changed.** Both directions matter: a test that passes while the behavior is broken is
a hole; a test that fails when structure changes with behavior intact is a corrupted
signal that teaches everyone — humans and goal loops — to distrust red.

## Assert outcomes, not choreography

Assert observable results: the response, the file, the database row, the exit code.
"The service called `repo.save(x)`" fails on restructuring with behavior intact.
Assert an interaction only when the interaction *is* the contract ("exactly one
notification sent").

## A unit is a behavior at the process boundary

Write tests through the smallest *stable* public surface — a service function, an
engine entry point, the in-process API (an ASGI test client makes no network calls) —
and let everything inside the process run real. Speed comes from avoiding I/O, not
from avoiding your own code: calling your own functions costs nanoseconds, and the
<100ms budget survives running the entire domain layer.

## Fakes at the seams, not patches in the guts

Replace only what is slow or non-deterministic — network, database, subprocess, LLM
calls, the clock — and prefer **hand-written fakes implementing a port** (in-memory
repository, fixed clock, canned responses) over `patch()`. A patch is welded to an
import path and a call signature, so it breaks when structure changes even though
behavior didn't; a fake survives any refactor that preserves the contract. Patching
first-party code is a coupling smell the structural gates count (the
`structural-gates` rule). Integration tests then have one precise job: prove each fake
honest by running the same contract suite against the real adapter.

## Acceptance tests carry extra constraints

They are the milestone's blocking criteria, so beyond the bar above:

- **Authored at planning time, before implementation exists** — nothing about the
  implementation can leak in. They exercise the brief's pinned Surface end-to-end.
- **Verifiable by a stranger** — real calls, observable state changes; a test that
  can pass while the job is undone is a hole in the contract itself.
- **Read-only during execution** — an executor that believes one is wrong escalates
  (the escape valve); the tests are writable only in planning and re-planning
  sessions. Grader and graded stay separate people.
