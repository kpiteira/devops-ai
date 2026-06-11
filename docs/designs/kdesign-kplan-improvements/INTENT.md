> **ARCHIVED (2026-06-11).** Investigated during the loop-quality-gates effort: every concern in this intent had already landed in kdesign/kplan v0.2.0 (JTBDs, human-action checkpoints, implementation-readiness, negative space). Kept for the provenance of the core observation — "every high-leverage improvement came from Karl intervening, not from the skills prompting it" — which motivated the verifier-first redesign (structural gates, kloop, machine-checkable milestone files).

# Improving kdesign & kplan — JTBD Traceability, Human-Action Visibility, Implementation-Readiness

**Date:** 2026-05-27
**Status:** Proposal / Intent (pre-design)
**Authors:** Karl + Lux
**Provenance:** CashFlow Pro MVP — one continuous design→plan→build pass:
- `/kdesign` session (produced `DESIGN.md`, `ARCHITECTURE.md`, 36 JTBDs, 5 milestones)
- `/kplan` session (produced `OVERVIEW.md`, full `M1`, `M2–M5` sketches)
- M1 implementation session (corrected two of the planning assumptions — see §5)

---

## 1. The core observation

Across a full design→plan→build cycle for a non-trivial feature, **every
high-leverage improvement to the output came from Karl intervening, not from the
skills prompting it.** The skills produced competent first drafts; the value was added
where Karl injected structure the skill didn't ask for.

| What Karl had to inject | Effect | Skill that should have prompted it |
|--------------------------|--------|-------------------------------------|
| "I want a comprehensive set of JTBDs, all matched to a milestone" | Forced full user-story coverage; **surfaced a scenario that was missing entirely** (a watchlist account) | kdesign |
| "tell me when I need to do something (like `/kinfra-onboard`) if it can't be automated" | Made human-only steps explicit instead of buried in prose | kplan |
| "Are the E2E tests validating the JTBDs from the design doc?" | Exposed that validation touched stories as a *flow* but proved none of them per-story | kplan |
| "Isn't there a ledger for past operations?" / "a read is a read" | Caught a command-query violation (a `GET` mutating state) and a temporal-model gap | kdesign (validation lens) |
| "any unresolved questions before kplan?" | Surfaced two painful-to-change **data-representation** decisions (amount sign model, liquidity flag) | kdesign (closing pass) |

Two of these (JTBDs, and the "validate the JTBDs" question) are the same idea seen
from the design side and the plan side. They are the headline change.

This document proposes concrete edits to `skills/kdesign/SKILL.md` and
`skills/kplan/SKILL.md`, prioritized, each grounded in what actually happened and —
where relevant — tempered by what the M1 build taught us.

---

## 2. kdesign changes

### 2.1 JTBDs as a mandatory, first-class artifact  ⭐ (highest leverage)

**Evidence.** The skill currently says to explore "user scenarios." That was vague
enough that the first design had a thin "scenarios" section and moved on. Only when
Karl asked for a *comprehensive, numbered, milestone-tagged* JTBD set did coverage
become real — and the act of enumerating them surfaced a capability (a watchlist
credit-card account) that nothing else in the design or the eventual E2E had captured.

**Problem.** "Scenarios" is treated as illustrative color, not as a coverage contract.
Nothing forces enumeration, IDs, or a mapping to milestones.

**Proposed change.** Make a JTBD set a required output of kdesign:
- Job-story form: *When ⟨situation⟩, I want to ⟨motivation⟩, so I can ⟨outcome⟩.*
- Each story gets a stable ID (`J1`, `J2`, …) and is tagged to exactly one milestone
  (the milestone where the job first becomes doable end-to-end).
- The milestone structure cross-references the IDs both ways (a "Stories" column), so
  the mapping is enforced from both sides.
- Include "tool/agent as a client" stories where the system is API-first (e.g. "When I
  hand Claude Code a screenshot, I want it to do everything the UI can via the API").

**Right-sizing caveat (must be in the skill).** Scale the JTBD set to feature
complexity. A 2-hour change does not need 35 job stories. The skill already has a
"right-sized" principle; the JTBD requirement must inherit it, or it becomes ceremony.

**Where it lands.** Add to "What This Produces"; add a "Jobs To Be Done" subsection
under "What to Explore" (before Milestones); make the Milestones step require JTBD tags.

---

### 2.2 An implementation-readiness pass before finishing  ⭐ (the sleeper)

**Evidence.** Karl's "any unresolved questions before kplan?" caught two decisions that
were *not behavioral* and *not state-machine* — they were data-representation choices:
- **Amount model:** signed amount vs. positive magnitude + direction-by-legs.
- **Liquidity:** hardcode-by-type vs. a per-account `counts_as_liquid` flag.

Both are cheap to decide on a whiteboard and expensive to change after schema + engine
exist. The kdesign gap-hunting found none of them because all its lenses point at
*behavior* (state transitions, error paths, concurrency).

**Problem.** kdesign has no lens for "how is this entity *shaped* in storage and on the
wire?" — the representation decisions that calcify the moment code is written.

**Proposed change.** Add a closing **Implementation-readiness check** to kdesign: a
short checklist run before declaring the design done. Candidate items:
- **Units & money:** currency, decimal precision, integer-cents vs decimal.
- **Sign/direction conventions:** signed values vs magnitude+direction.
- **Identity:** id scheme; any synthetic/derived ids; uniqueness keys.
- **Enums & nullability:** closed sets named; which fields are optional and why.
- **Time:** date vs datetime; timezone ownership; is "now" injectable?
- **Side-effects / purity:** which operations are pure reads? (see 2.3)

Each item is a one-line decision or an explicit "deferred to milestone N (low risk)."

**Where it lands.** New section after "Validation," before "Output." Frame it as the
hand-off contract to kplan: "these are the choices kplan will otherwise invent in code."

---

### 2.3 A command-query / side-effect lens in the gap categories  (medium)

**Evidence.** Karl caught that `GET /ledger` was mutating the detachment frontier ("a
read is a read"). The fix reshaped the architecture (a scheduled sweep + write-path
triggers; pure reads). The brief had even *invited* the smell ("no cron").

**Problem.** kdesign's gap categories are: state-machine, error-handling, data-shape,
integration, concurrency. None ask "where do side-effects live / are reads pure?"

**Proposed change.** Add a gap category: **Side-effect / command-query gaps** — "Does a
read mutate state? Does an operation have a side-effect its name doesn't imply? Where
does each state change get triggered, and is that the same surface as the read?" This
is general (CQS) and would have surfaced the frontier issue without Karl.

**Where it lands.** "Validation → Gap categories to look for."

---

## 3. kplan changes

### 3.1 Mandate JTBD ↔ milestone ↔ E2E traceability  ⭐ (highest leverage; enforcement half of 2.1)

**Evidence.** "Are the E2E tests validating the JTBDs?" — honest answer at the time was
*no*: the M1 validation exercised stories as a flow but asserted none per-story, and
one story (watchlist) wasn't even in the scenario. We added a "Stories" column to the
milestone table and a JTBD-coverage table to each VALIDATION task; the latter
immediately exposed the missing assertion.

**Problem.** kplan mandates *that* a VALIDATION task exists, but not that it proves the
milestone's user stories. "Validated" can mean "the flow ran," not "every job this
milestone owns is observably satisfied."

**Proposed change.** Make story traceability structural:
- The milestone table carries a **Stories** column (the JTBD IDs the milestone owns).
- Every VALIDATION task carries a **JTBD coverage audit**: each owned JTBD → the
  concrete assertion that proves it + the evidence captured. A milestone is not
  validated until each owned JTBD has a passing, evidence-backed assertion.
- A consistency check: every JTBD from the design appears in exactly one milestone's
  Stories column, and every JTBD has ≥1 covering assertion.

**⚠️ Tempered by M1 implementation — DO NOT conflate coverage with recipe count.**
During the build, Karl pushed back twice on recipe granularity: first against one
monolithic per-milestone recipe, then against over-correcting to one-recipe-per-JTBD.
The settled model (now a CashFlow memory): **ke2e recipes are reusable,
capability-scoped building blocks the scout composes across milestones** — each stands
alone with minimal setup, covers a single capability, and is reusable in future
milestones (e.g. `ledger/read-purity` is reused by any `GET`). Therefore:
- The JTBD-coverage table is an **audit/mapping over assertions**, not a recipe-per-JTBD
  structure. One reusable recipe may satisfy assertions for several JTBDs; one JTBD may
  be proven by assertions spread across recipes.
- kplan should describe recipes as capability blocks and explicitly warn against both
  failure modes (one-giant-recipe and rigid-one-per-JTBD).

**Where it lands.** "Architecture Alignment" (add story traceability) and "VALIDATION
Tasks" (add the coverage-audit requirement + the capability-block framing).

---

### 3.2 Human-action callouts  ⭐ (workflow-critical)

**Evidence.** The first plan buried `/kinfra-onboard` in prose as if automatic. Karl:
"tell me when I need to do something … if it cannot be done automatically." We added a
`👤 HUMAN ACTION` convention inline at the exact task step, plus a consolidated
checklist in OVERVIEW.

**Problem.** kbuild needs to know precisely when to stop and hand control to the human
(interactive logins, infra onboarding, secret provisioning, PR review/merge). The skill
never asks the planner to surface these.

**Proposed change.**
- Add an optional **Human action** field to the Task Structure template, used whenever a
  step can't be automated, placed at the exact point it's needed.
- Require a consolidated **Human-action checkpoints** table in OVERVIEW (when / action /
  why-not-automatable).

**⚠️ Tempered by M1 implementation — the infra story I wrote was wrong.** The plan told
Karl to run `/kinfra-onboard` after the compose file lands, and to validate against a
"kinfra sandbox." Reality (now a CashFlow memory):
- **Onboarding is one-time `kinfra init`** (generates `.devops-ai/infra.toml`,
  parameterizes compose, Justfile/pre-commit/CI). It is *not* a per-milestone step.
- **A kinfra *sandbox* comes only from `kinfra impl <feature>/<milestone>`, which forks
  a NEW worktree from `main`** — useless for a hand-made feature-branch worktree, and
  Karl rejected the worktree gymnastics outright.
- **Per-milestone E2E runs against the local `docker compose` stack in the current
  worktree** (real HTTP at `localhost:PORT`, reset DB between aggregate-asserting
  recipes).

So the skill guidance must (a) distinguish one-time onboarding from per-milestone
validation infra, and (b) default E2E to "the current worktree's compose stack," not a
sandbox that forks main. This is a concrete gotcha worth encoding in both kplan's
human-action guidance and the VALIDATION task's pre-flight.

**Where it lands.** "Task Expansion → Task Structure" (new field), "Output Structure"
(OVERVIEW must include the checklist), and a note in "VALIDATION Tasks" about the
compose-vs-sandbox default.

---

### 3.3 Just-in-time planning depth as an explicit, named mode  (medium-high)

**Evidence.** kplan reads as "expand all milestones into full tasks." We instead did
**full M1 + sketches for M2–M5 + re-plan-before-build**, and it was the right call:
M4/M5 detail would have been reworked once M1–M3 surfaced integration learnings (as
indeed happened — see the two M1 corrections above). Karl explicitly endorsed and asked
to confirm the "re-run kplan per milestone later" loop.

**Problem.** The skill's default invites over-investment in far-milestone detail that is
predictably reshaped by earlier milestones.

**Proposed change.** Add a **Planning depth** subsection offering two modes, recommending
the first for multi-milestone work:
- **Just-in-time (recommended):** OVERVIEW (all milestones, deps, branch strategy) +
  full tasks for the next milestone + lightweight sketches (goals, key tasks, risks) for
  later ones, each marked "SKETCH — re-plan before build." Re-run kplan scoped to one
  milestone before kbuild executes it, feeding the prior milestone's handoff.
- **Full up-front:** every milestone fully expanded — for short or highly-stable plans.

**Where it lands.** New subsection under "Task Expansion"; reference it from "Output
Structure" (sketch files are legitimate milestone files).

---

### 3.4 Sharpen the consistency check for dependency *direction*  (medium)

**Evidence.** I parked month-low/overdraft *computation* in M5 while M4 *rendered* it —
a backwards dependency. The current consistency check ("dependency ordering is correct")
didn't catch it; I only found it by manual scan.

**Problem.** "Ordering correct" is about prerequisites, not about a later milestone's
*output* being consumed earlier.

**Proposed change.** Add a consistency-check bullet: **"No milestone consumes or renders
an artifact that a later milestone produces."** When found, either move the producer
earlier or split it.

**Where it lands.** "Output Structure → Consistency Check."

---

## 4. Cross-cutting: close the build→design feedback loop

The two M1 memories that corrected this plan (recipe granularity; compose-not-sandbox)
are exactly the kind of learning that should flow back into the skills — yet today it
only happens because Karl carries it between sessions. Worth considering (not
necessarily now): a lightweight convention where a milestone handoff flags "skill
assumption X was wrong" so the next kplan/kdesign run (or a periodic skill review) can
absorb it. This document is a manual instance of that loop.

---

## 5. Prioritization

| # | Change | Skill | Leverage | Notes |
|---|--------|-------|----------|-------|
| 2.1 | JTBDs as required artifact | kdesign | ⭐ High | Headline; pairs with 3.1 |
| 3.1 | JTBD↔milestone↔E2E traceability | kplan | ⭐ High | Enforcement; respect capability-block nuance |
| 3.2 | Human-action callouts | kplan | ⭐ High | Fix the compose-vs-sandbox framing too |
| 2.2 | Implementation-readiness pass | kdesign | High | The sleeper — catches representation decisions |
| 3.3 | Just-in-time planning depth | kplan | Med-High | Workflow; already validated in practice |
| 3.4 | Dependency-direction check | kplan | Medium | Small, sharp |
| 2.3 | Command-query / side-effect lens | kdesign | Medium | General CQS hygiene |

**Recommended first cut:** 2.1 + 3.1 + 3.2 (with the two implementation corrections),
then 2.2. The rest can follow.

---

## 6. Open questions for the design pass

1. **JTBD home** — own section in kdesign output, or folded into DESIGN.md? (CashFlow put
   them in DESIGN.md §9; worked well.)
2. **Coverage-audit format** — a table in each VALIDATION task (what we did) vs a single
   milestone-level matrix. Must stay decoupled from recipe count (3.1).
3. **Implementation-readiness checklist** — fixed list vs. project-type-aware (Python vs
   TS vs infra surface different representation traps).
4. **Where the compose-vs-sandbox guidance belongs** — kplan only, or also a rule
   (`e2e-testing.md`) since it's a cross-skill operational fact?
5. **Feedback-loop mechanism (§4)** — in scope for this effort, or a separate one?

---

## 7. Concrete edit appendix (starting points, not final wording)

**kdesign/SKILL.md**
- *What This Produces:* add "4. **Jobs To Be Done** — numbered job stories, each tagged
  to a milestone."
- *What to Explore → new "Jobs To Be Done" subsection:* job-story form, IDs, milestone
  tags, client-as-user stories, right-sizing caveat.
- *Validation → Gap categories:* add "Side-effect / command-query gaps."
- *New section "Implementation-readiness check"* (after Validation): the representation
  checklist from 2.2.
- *Milestones:* require each milestone to list the JTBD IDs it delivers.

**kplan/SKILL.md**
- *Architecture Alignment:* add story-traceability extraction (which JTBDs each milestone
  owns).
- *Task Expansion → Task Structure:* add optional `**Human action:**` field.
- *New subsection "Planning depth"*: just-in-time vs full up-front (3.3).
- *VALIDATION Tasks:* add the JTBD-coverage-audit requirement; add the "recipes are
  reusable capability blocks (not one-giant, not one-per-JTBD)" framing; add the
  "E2E against the current worktree's compose stack, not a main-forking sandbox"
  pre-flight note.
- *Output Structure:* OVERVIEW must include a Human-action-checkpoints table; sketch
  milestone files are legitimate; add the dependency-direction consistency bullet (3.4).
