# Strain Log — where the framework's rails chafe against Opus 4.8

**Purpose.** Evidence for the de-restriction work (see `INTENT.md` §1, §5). We do **not** trim off
vendor benchmarks — we trim off *this*. Captured live while building **CashFlow Pro** on Opus 4.8
with the current framework.

**What to capture here** — the framework being too *restrictive*:
- A prescriptive rail forced the model onto a worse path than it would have chosen.
- The model visibly worked *around* a prescription (a tell that the prescription fights it).
- The model would plausibly have done better given just the goal + the contract, not the steps.
- A `MANDATORY`/`MUST` produced ceremony with no engineering payoff in this instance.

**What does NOT go here** — that's a different failure direction:
- The framework being too *weak* / under-prompting (Karl had to inject structure the skill should
  have asked for) → that belongs to `../kdesign-kplan-improvements/INTENT.md`.
- A genuine bug in a skill → fix it directly.

**Discipline.** Capture in the moment, terse. Don't pre-judge whether the rail should be relaxed —
that's the synthesis step once there's enough signal. A rail that chafes *once* may still be
earning its keep; we look for patterns.

---

## Entry template

```
### YYYY-MM-DD · <skill> · <one-line summary>
- **Rail:** <the specific instruction/phase/imperative involved — quote it if short>
- **What happened:** <what the model did, or wanted to do, and how the rail intervened>
- **Category:** forced-suboptimal | worked-around | would-do-better-free | empty-ceremony
- **What to relax (hypothesis):** <one line — held loosely, not a commitment>
- **Counter-check:** <is the rail a verification/contract (likely keep) or method-restriction (candidate to relax)?>
```

---

## Illustrative example (hypothetical — delete once real entries exist)

### 2026-05-28 · kbuild · phase-ordering forced research after a path was already clear
- **Rail:** "Research first (design + arch + existing code + patterns)" as a mandatory opening step.
- **What happened:** For a one-line fix to an already-understood module, the model dutifully ran a
  full research pass it didn't need, because the skill presents research as a non-skippable phase.
- **Category:** empty-ceremony
- **What to relax (hypothesis):** Frame research as "build the context you lack" (goal) rather than
  "do this phase" (step) — let the model scale it to what it already knows.
- **Counter-check:** Method-restriction, not a contract. Candidate to relax. (TDD RED-first in the
  same skill is a *contract* — would NOT go in this log even if it felt like overhead.)

---

## Real entries

_(none yet — add as you build CashFlow Pro on Opus 4.8)_
</content>
