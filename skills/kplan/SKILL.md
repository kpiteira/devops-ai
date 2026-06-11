---
name: kplan
description: Expand milestones into implementable tasks with architecture alignment, JTBD traceability, TDD requirements, and E2E validation.
metadata:
  version: "0.4.0"
---

# Implementation Planning Command

Expand a design's milestones into implementable tasks. Each task is self-contained — someone
reading only that task should be able to implement it.

## What this produces

- **OVERVIEW.md** — milestone summary, dependency graph, branch strategy, human-action checkpoints.
- **One file per milestone** (M1_name.md, …) — tasks with files, behavior, tests, acceptance.

```
/kplan design: <DESIGN.md> arch: <ARCHITECTURE.md>
```

## This is a conversation

Claude proposes milestones and tasks; you adjust. Milestone boundaries and split/merge calls are
judgment — you know team capacity, hidden complexity, and what belongs together as a unit.

## Architecture alignment (before planning tasks)

Understand the architecture's core decisions first — this is what prevents implementation drift,
the most expensive planning failure. From the architecture doc, extract the core patterns (state
machine? worker model? event-driven?), the key decisions and what they mean for task design, and
what's explicitly ruled out. Confirm these with the user before proceeding: if the architecture
says "state machine with explicit transitions," no task should quietly introduce a polling loop.
Every task traces back to an architectural decision — a task introducing an unplanned pattern means
either the architecture needs updating or the task is wrong.

**Also extract the JTBD → milestone mapping** from the design. Each milestone owns a set of job
stories (the IDs kdesign tagged). That ownership becomes a coverage contract, enforced below.

**And extract the Enforcement table** from ARCHITECTURE.md — the invariant entries become M1's
gate-harness task, and the review-lens entries ride along in each milestone's STRUCTURE task
(both below). If the architecture has no Enforcement table, that's a kdesign gap: surface it
before planning, don't invent contracts.

## A plan is graded on the negative space too, not just the jobs

JTBDs are aspirational — "when X, I want Y" — so a plan drawn purely from them is a happy-path
plan, and the rigor it omits (reject bad input, hold invariants, don't corrupt state when
features combine) gets discovered in review instead, at the highest cost the loop has. So a good
milestone plan clears a higher bar than "every JTBD has a task." It also accounts for:

- **What must be rejected**, not just accepted — the malformed, out-of-range, out-of-contract
  inputs each new write turns away, and how (null where non-null, future-dated when "past" is
  implied, unknown references), so they're planned as behavior rather than found as 500s.
- **What must always be true** — the invariants worth enforcing at the lowest honest layer (a
  CHECK/unique constraint, an impossible state-machine transition) rather than trusting every
  call site, because the constraint is what holds when a later bug or manual write doesn't.
- **What shares state** — which prior-milestone features touch the same table / dedup key /
  balance walk as this one, because those pairings are where combined behavior corrupts while
  per-feature tests stay green.

You don't need a rigid template for this. But a plan that names only its happy-path jobs has left
its most expensive defects for review to find — so carry these into the task tests and the
VALIDATION assertions, and let kbuild's close-out interaction-surface bar verify them.

## Planning depth — just-in-time by default

For multi-milestone work, expanding every milestone into full tasks up front is usually wasted
effort: later milestones get reshaped once earlier ones surface integration learnings. Prefer:

- **Just-in-time (default):** OVERVIEW (all milestones, dependencies, branch strategy) + full tasks
  for the *next* milestone + lightweight sketches (goal, key tasks, risks) for later ones, each
  marked **"SKETCH — re-plan before build."** Re-run kplan scoped to one milestone before kbuild
  executes it, feeding in the prior milestone's handoff.
- **Full up-front:** every milestone fully expanded — for short or highly stable plans.

A sketch file is a legitimate milestone file. Don't invent detail for a milestone you'll re-plan.

## Task expansion

A task is implementable by someone who reads only it. That means: **files named** (not "update the
service" but `src/services/user.py`), **behavior described** (not "add validation" but "validate
the symbol exists in cache before starting download"), **tests specified** (not "add tests" but
"returns 404 if symbol not found"), **patterns referenced** (not "follow existing patterns" but
"follow `UserService.create()`"). Split anything over ~4 hours.

```markdown
## [ ] Task N.M: [Title]

**File(s):** [specific files to create/modify]
**Type:** CODING | RESEARCH | MIXED | STRUCTURE | VALIDATION
**Estimated time:** [1–4 hours]
**Verify:** [the command that proves this task — exits 0 only if the behavior works, e.g. `uv run pytest tests/unit/test_user.py -q`]
**Human action:** [only if a step can't be automated — see below; omit otherwise]

**Description:** [what it accomplishes — specific about behavior]
**Implementation Notes:** [patterns, gotchas, integration points]
**Testing Requirements:** [ ] [specific cases — happy path, **rejected bad input**, edges, and any **interaction** with a prior-milestone feature that shares this state]
**Acceptance Criteria:** [ ] [verifiable]
```

For tasks spanning multiple categories (persistence, wiring, state machines, …), identify each
category's failure modes and add matching integration tests. The `kplan-categories.md` reference has
the full taxonomy — load it when analyzing task types.

**The milestone file is goal state, not prose.** The loop that executes it (kloop) and a `/goal`
evaluator treat it as the completion contract: tasks are worked first-unchecked-first, and a
checkbox flips to `[x]` only when the task's **Verify** command exits 0 — evidence, not the
implementer's claim. So write Verify to actually discriminate: the test selector that fails if
this task's behavior is wrong (`make check` runs on every task regardless — don't restate it).
A task whose done-condition can't be a command gets the closest runnable proxy plus a named
review-lens in the STRUCTURE task — never "done when it looks done."

**Human-action callouts.** kbuild needs to know exactly when to stop and hand control to a human —
interactive logins, secret provisioning, PR review/merge, one-time infra setup. Mark those at the
exact step with the `Human action:` field, and collect them into a **Human-action checkpoints**
table in OVERVIEW (when / action / why it can't be automated). Don't bury a manual step in prose as
if it were automatic.

One such step is frequently mis-described, so state it correctly:
- **Onboarding is one-time `kinfra init`** (generates `.devops-ai/infra.toml`, parameterizes
  compose, Justfile/pre-commit/CI). It is *not* a per-milestone step.
- **Per-milestone E2E runs against the current worktree's `docker compose` stack** (real HTTP at
  `localhost:PORT`, DB reset between aggregate-asserting recipes) — *not* a `kinfra impl` sandbox,
  which forks a new worktree from `main` and is the wrong tool for a hand-made feature branch.

## Structural gates in the plan

Two structural requirements, mirror-images of the VALIDATION rule below:

- **M1 carries the gate-harness task:** copy `templates/test_invariants.py` from the devops-ai
  repo (locate it by resolving the skill symlink: `readlink ~/.claude/skills/kplan` → its parent
  repo) into `tests/architecture/`, port the ARCHITECTURE.md Enforcement table into contracts,
  and freeze ratchets for pre-existing violations. kinfra-generated Makefiles already run
  `tests/architecture/` inside `make check` (a `kinfra init` re-run refreshes older ones), so
  pre-commit, CI, and the Stop hook all enforce it with no extra wiring. The gate exists
  *before* the code it must constrain — it is not a retrofit step.
- **Every milestone's task list ends STRUCTURE, then VALIDATION.** The STRUCTURE task is
  kbuild's milestone-close structure pass (whole-diff consolidation review, findings fixed
  in-milestone) made visible in the plan so it can't be skimmed past. List the Enforcement
  table's review-lens entries in the task description — they are the lenses the reviewing
  subagent must carry.

## VALIDATION tasks

Every milestone ends with a VALIDATION task — a structural requirement, because "unit tests pass"
is not "the system works." Its description carries these instructions, which kbuild reads at
execution time:

1. Load the `ke2e` skill.
2. Invoke **ke2e-test-scout** with the milestone's validation requirements — it searches the
   catalog and returns matching recipes, or hands off to ke2e-test-designer for new ones.
3. Invoke **ke2e-test-runner** with those recipes — it runs pre-flight checks against the real
   sandbox/compose stack and reports PASS/FAIL with evidence.
4. **E2E means real external calls** — real APIs, real containers, real state changes, observable
   outcomes. A test that mocks or seeds data without real calls is an integration test: write it if
   useful, but it does not satisfy validation. "Does it start" is not validation.

**Prove the JTBDs, don't just run the flow.** Each VALIDATION task carries a **JTBD coverage
audit**: for every job story the milestone owns, the concrete assertion that proves it and the
evidence captured. A milestone isn't validated until each owned JTBD has a passing,
evidence-backed assertion.

**Validation covers the negative space too**, not only the happy-path JTBDs. A system that does
the right thing on good input but 500s or corrupts state on bad input, or when two features that
share state combine, is not validated — so the assertions include the trust-boundary rejections
and the cross-feature scenarios the plan named (see "A plan is graded on the negative space too").

⚠️ **Coverage is an audit over assertions — not a recipe count.** ke2e recipes are reusable,
capability-scoped building blocks the scout composes across milestones (e.g. `ledger/read-purity`
is reused by any `GET`). One recipe may satisfy assertions for several JTBDs; one JTBD may be
proven by assertions spread across recipes. Avoid both failure modes: one monolithic
per-milestone recipe, *and* a rigid one-recipe-per-JTBD. The coverage table maps JTBDs to
assertions, not to recipes.

## Output

```
docs/designs/<feature>/
  DESIGN.md
  ARCHITECTURE.md
  implementation/
    OVERVIEW.md
    M1_<name>.md   ...
```

Each milestone file carries frontmatter so kbuild can discover context:

```markdown
---
design: docs/designs/<feature>/DESIGN.md
architecture: docs/designs/<feature>/ARCHITECTURE.md
---
```

The milestone table carries a **Stories** column (the JTBD IDs each milestone owns).

**Consistency check before saving.** Every major design decision appears in at least one task;
every architectural pattern has implementing tasks; no task uses a ruled-out approach; dependency
ordering is correct; **every task heading carries an unchecked `[ ]` and a Verify command that
discriminates** (a Verify that passes before the task is implemented proves nothing); **every
JTBD appears in exactly one milestone's Stories column with ≥1 covering assertion**; **every
invariant in the Enforcement table lands in M1's gate-harness task and every milestone ends
STRUCTURE → VALIDATION**; and **no milestone consumes or renders an artifact a later milestone
produces** (a backward dependency — move the producer earlier or split it).

## Integration

kplan sits between `/kdesign` (produces the design + JTBDs) and execution — `/kloop` (the
autonomous loop, one task per fresh context) or `/kbuild` (the attended fallback). The milestone
files are the interface contract between planning and execution. When a build surfaces a wrong
planning assumption, that belongs in the handoff so the next kplan run absorbs it.
</content>
