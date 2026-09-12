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

### The acceptance-test checklist

Every item below was a hole in the first pilot. The planner works through it before the
sign-off walkthrough, and the brief's Blocking table shows the result.

- **If a test asserts it, the Surface states it.** A grader that pins more than the brief
  is the planner deciding shape silently.
- **Opposite reading.** For each decision the human cares about: would this test pass
  under the opposite reading? If yes, it pins nothing — pin it, or mark the decision as
  the human's to make.
- **Measured on main.** Every "passes/fails on main" claim is measured in the
  executor's runtime (a running sandbox where the project has one); the Blocking
  table records the command and its output.
- **The executor's runtime, not the planner's.** Sandbox ports (`base + slot`),
  environment, and **clock and timezone** — a test that reads the runner's `today()`
  while the server judges days in the user's timezone is green on one laptop and red
  everywhere else.
- **Run-to-the-end.** At least one scenario per lifecycle the feature introduces runs it
  to its final state; the pilot's only intent drift lived past the last day nobody tested.
- **Rendered output for UI jobs.** Never a source substring: it fails a correct refactor
  and passes a broken render. Assert the SSR or compiled output, or drive a browser.
- **Failure path.** For every external side effect the Surface pins, one test for the
  channel being down.
- **Integration-level, labeled.** When the live stack cannot exercise a job, an
  integration-level blocking test is legal if the Blocking table says so, says why, and
  carries its measured baseline.
