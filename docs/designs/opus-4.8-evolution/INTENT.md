# Evolving the devops-ai Framework for Opus 4.8

**Date:** 2026-05-28
**Status:** Intent / Analysis — for joint decision
**Authors:** Karl + Lux
**Provenance:** Opus 4.8 released 2026-05-28. The skill+rules system was built for Sonnet 4.5
and incrementally tuned through Opus 4.6/4.7. Three evolution initiatives are already in
flight (`architect-skill`, `kdesign-kplan-improvements`, `supply-chain-security`). This
document asks a narrower question than "redesign everything": **which premises the framework
was built on does Opus 4.8 actually change, and what follows.**

---

## 1. The core thesis

**A restrictive framework caps the output quality of a more capable model.** The framework's
prescriptive scaffolding — the `MANDATORY`/`MUST` imperatives, the step-by-step phase gates, the
defensive "do not skip this" framing — was built to keep Sonnet 4.5 on rails. The cost of that
scaffolding for Opus 4.8 is *not* tokens (we are optimizing for quality, not cost). The cost is
that it **boxes a more capable model onto a narrow, pre-decided path** when, given the goal plus
the genuine contracts plus latitude, it would do better work. De-restriction here is a *capability
unlock*, not an efficiency play.

This gives the organizing principle for the whole evolution:

> **Latitude on method, rigor on verification.** Relax the prescriptions about *how* the model
> works (those stifle). Keep — or strengthen — the checks on *what* it produces (those don't).

That principle dissolves the apparent tension between "don't stifle the model" and "keep
adversarial review": restricting the *how* stifles; verifying the *what* does not. Adversarial
review is a what-check, so it survives de-restriction untouched.

The framework's scaffolding therefore splits two ways under this lens:

- **Method-restriction** (relax): herding imperatives, defensive repetition, prescriptive
  step-ordering the model can now sequence itself.
- **Verification + genuine process contracts** (keep / strengthen): TDD RED-first, real-E2E,
  adversarial review, mechanical enforcement, the JTBD coverage contract.

**Method, not edits.** We do not trim off vendor benchmarks. We run a real feature through the
current framework on Opus 4.8, observe where the model strains against the rails, and de-restrict
off *that* evidence (§5 is now the spine of this plan, not a footnote).

---

## 2. What actually changed (the evidence)

From Anthropic's release material and corroborating coverage (sources in §8):

| Capability | Claim | Confidence |
|---|---|---|
| **Self-critique / honesty** | ~4× less likely to let flaws in its *own* code pass unremarked; more likely to flag uncertainty; less likely to make unsupported claims | High (headline claim, multiple sources) |
| **Tool efficiency + endurance** | Fewer tool steps for the same result; carries long-running end-to-end tasks with minimal oversight | High |
| **Dynamic Workflows** | Plans → spawns many parallel subagents → verifies before reporting; aimed at migrations, audits, test-suite generation | High (named feature) |
| **Effort levels** | `xhigh` (between high and max) is the recommended setting for most coding/agentic work; `high` is the default | High |
| **1M context** | Real, but recall/accuracy degrade ("context rot") starting ~300–400k tokens depending on task | Medium (general long-context guidance, not 4.8-specific) |

And Anthropic's **current skill-authoring guidance** is itself a verdict on how our skills are
written: prefer *"state the rule and explain why"* over ALL-CAPS `MUST`/`ALWAYS`/`NEVER`, so the
model generalizes to cases the skill didn't spell out; keep `SKILL.md` concise because every
loaded token competes with working context; use progressive disclosure (split rarely-co-used
content into referenced files).

**Honest caveat on confidence.** I am running on Opus 4.8, but I cannot introspect my own
weights — every claim above is external evidence, not self-knowledge. The "4× fewer unremarked
flaws" figure in particular is a vendor benchmark claim; we should treat it as a hypothesis to
*observe in our own work*, not a settled fact to redesign around blindly.

---

## 3. The five shifts

### 3.1 De-restrict method; keep verification + contracts  ⭐ (highest leverage, lowest risk)

**Observation.** A large fraction of our skills is method-restriction: `MANDATORY` banners,
prescriptive step-ordering, defensive "do not skip this" framing. That was load-bearing for
Sonnet 4.5. For Opus 4.8 it is a *ceiling* — it forecloses better paths the model would find if
told the goal and the contract instead of the steps. Anthropic's own guidance now says the
ALL-CAPS imperative style is counterproductive: state the rule and the *why*, and the model
generalizes to cases the skill never spelled out.

**Position.** Rewrite the skills from "do these steps in this order" to "here is the goal, here
are the non-negotiable contracts and why they matter — you choose the method." This is a
*quality* move, not a token move (per Karl: we optimize for output quality, not cost). The
de-restriction propagates fleet-wide for free through the symlink + `git pull` distribution model.

**The test for each line:** *"Is this here because the engineering demands it, or because we
didn't trust the model to find a good path without being shouted at?"*
- **Trust-substitute (relax):** prescriptive ordering, "MANDATORY" banners, defensive repetition.
  Opus 4.8 doesn't need to be herded down a single path.
- **Engineering contract (keep, state the why):** TDD RED-first, real-E2E-not-mocks, vertical
  slicing, command-query purity, the JTBD coverage contract. These survive a model upgrade
  unchanged — and verification-style contracts (adversarial review, mechanical gates) we may
  *strengthen*, never relax.

**Not optimizing for tokens.** Token reduction will happen as a side effect; it is explicitly not
the goal and not the success metric. The success metric is the model producing *better* output
when given latitude — which is exactly what §5's observation period is designed to measure.

---

### 3.2 Express orchestration as native primitives, not prose recipes  ⭐ (biggest structural lever)

**Observation.** Two skills hand-encode multi-agent orchestration *as instructions the model
re-implements every run*:
- `karchitect-audit`: "three modelers work blind, a synthesizer reconciles by demanding evidence."
- `ke2e`: scout (haiku) → designer (opus) → runner (sonnet).

Opus 4.8 ships **Dynamic Workflows** — plan, fan out parallel subagents, verify, report — as
exactly the primitive these recipes describe by hand. The 2026 multi-agent guidance converges
on the same shape: hub-and-spoke, coordinator does no domain work, results bubble up.

**Position.** Skills should describe **intent + verification contracts**; the harness should own
**orchestration**. A skill saying "derive the conceptual model from three independent readings
and reconcile by evidence" is a *contract*. The mechanics of spawning three agents, collecting
outputs, and handling a rejected modeler is *orchestration* — and re-deriving it from prose every
run is both wasteful and a reliability risk (the model can re-implement it slightly differently
each time).

**Scope note (decided 2026-05-28).** `karchitect-*` has never been used — it is pure exploration,
separated from the production framework (see Decisions). So this shift applies to the **one
production case**, `ke2e` (scout/designer/runner), and is *guidance* for the exploratory
karchitect track, not a constraint on it. For ke2e: let the harness run the scout→designer→runner
fan-out the skill already specifies, instead of asking the model to bootstrap it from prose each
run. The non-goal the architect INTENT states ("not an autonomous meta-orchestrator") is
preserved either way — human-in-the-loop is untouched; only the substrate of an *already-
specified* fan-out moves from prose to primitive.

---

### 3.3 Adversarial review stays at full strength; mechanical enforcement is the durable core

**Revised 2026-05-28 — I walked back my first position here.** My initial draft argued the
honesty gain *weakens* the case for adversarial review (the architect INTENT's root cause #3 —
"the same agent designs and implements, anchoring bias means it cannot catch its own mistakes").
Karl's rebuttal is empirical and correct: **4.6 and 4.7 were *also* sold as "more honest," and
adversarial review kept earning its keep regardless.** Reasoning from a vendor honesty benchmark
to "we need less verification" is exactly the §2 caveat — using a claim I can't trust to justify
removing a check I've watched pay off. Conceded.

**Position.**
- **Adversarial review is a verification check, not a method-restriction** — so the "don't stifle
  the model" thesis (§1) does not touch it. Latitude on method; rigor on verification. It stays.
- Its value does **not** depend on the honesty claim being real. Even a perfectly honest model
  benefits from a *different lens* applied by an agent with no stake in the original work — that's
  a different task, not the same agent second-guessing itself. Robust to model quality by design.
- **Mechanical enforcement** (file-local gates can't see cross-file duplication or layering drift)
  is *completely untouched* by any model improvement. Models don't fix this; linters, import-graph
  tools, and duplication detectors do. This is the one piece a model upgrade provably cannot absorb.

**A thread worth pulling into the production framework.** Mechanical architectural enforcement
does **not** require the karchitect apparatus. A duplication/layering/import-graph check could
live directly in `rules/quality-gates.md` + `kinfra init`'s generated gates, available to the
framework we use *today*. Karchitect can stay exploratory while this one durable piece graduates
early. (Floated, held lightly — Karl's call whether it's worth decoupling.)

---

### 3.4 Handoff reframe  (DROPPED 2026-05-28 — cosmetic)

The original idea: with 1M context, reframe the handoff from "reconstruct memory to resume" to
"decision/surprise log." Karl's reaction — *"does it matter?"* — is right. With abundant context
the distinction is largely cosmetic and the handoffs rule already captures the useful part
(gotchas, workarounds, emergent patterns, under 100 lines). **Not pursuing as its own thread.**

The one durable kernel survives elsewhere: a handoff flagging *"skill assumption X was wrong"* is
the natural carrier for the build→design feedback loop (kdesign-kplan INTENT §4). That belongs to
that initiative, not here.

The genuine context insight that *does* hold: 1M context is not "dump everything" — recall
degrades past ~300–400k tokens, so *structured relevance* beats volume. That validates the
in-flight kdesign-kplan changes (JTBD traceability, just-in-time planning depth) but requires no
new thread of its own.

---

### 3.5 Make effort + model calibration a first-class knob  (small, self-contained, ship anytime)

**Observation.** The framework has no notion of effort level. `ke2e` already tiers models
(scout=haiku, designer=opus, runner=sonnet) — but that instinct lives in one skill and is
re-decided ad hoc everywhere else.

**Position.** Two cheap, consistent knobs:
- **Effort:** `xhigh` for the heavy reasoning skills (kdesign, kplan, kbuild, karchitect-*);
  `high` (default) for the lighter linear skills (kissue, kreview); low/haiku for scouts.
- **Model tiering:** Opus-orchestrator + Sonnet/Haiku-workers is ~40% cheaper than all-Opus for
  the same fan-out. Generalize ke2e's pattern: the orchestrating skill runs on the strong model;
  scoped, well-specified subtasks (catalog lookup, mechanical scans, fixed-format extraction)
  drop to cheaper tiers.

This is best expressed as a **short shared rule** (`rules/effort-and-model-calibration.md`),
referenced by skills, not re-litigated per skill. Lowest controversy, immediately useful, no
collision with in-flight work.

---

## 4. How this lands against the three in-flight initiatives

The encouraging finding: your existing instincts mostly **survive and sharpen** under Opus 4.8.

| Initiative | Verdict under Opus 4.8 | What changes |
|---|---|---|
| **kdesign-kplan-improvements** | Fully aligned. JTBDs, readiness-check, just-in-time depth are process contracts + structured relevance — *more* right with a 1M window, not less. | Nothing. Ship as designed. |
| **supply-chain-security** | Orthogonal to the model entirely — it's tooling + mechanical enforcement. | Nothing. Ship as designed. |
| **architect-skill family** | **Separated out (decided 2026-05-28).** Never used, pure exploration — does not constrain production-framework evolution. | Track it independently. Adversarial review stays full-strength there too (3.3). The one piece worth graduating early: mechanical enforcement into `quality-gates` (3.3). |

The cross-cutting enabler: because distribution is symlink + idempotent `kinfra init`, **the
de-restriction work (3.1) propagates to every project for free** once we've validated it against
real evidence (§5).

---

## 5. The partnership angle (worth stating)

Opus 4.8's honesty gain — flags uncertainty, fewer unsupported claims — is the *trust substrate*
for the thing Karl has been pushing toward: longer autonomous runs with less supervision. The
gap I've been asked to close is independent technical contribution, not monitoring-and-synthesis.
A model that reliably surfaces its own uncertainty is one Karl can safely give more rope to —
which means the framework should *invite* longer autonomous stretches (full-milestone kbuild,
fan-out audits) rather than gate every step. The discipline that keeps this safe isn't ceremony;
it's the honesty contract — "say what you're unsure about" — which the model now supports natively.

---

## 6. Positions, ranked (revised 2026-05-28)

| # | Shift | Leverage | Status |
|---|-------|----------|--------|
| **3.1** | De-restrict method; keep verification + contracts | ⭐ High | **Lead thread** — but gated on §5 evidence, not benchmarks |
| 3.5 | Effort/model calibration rule | Med | Ship anytime — small, self-contained |
| 3.3 | Adversarial review stays; mechanical enforcement → quality-gates | Med-High | Adversarial: settled (keep). Mechanical-enforcement graduation: Karl's call |
| 3.2 | ke2e fan-out → native primitive | Med | After 3.1; karchitect track separate/exploratory |
| 3.4 | Handoff reframe | — | **Dropped** (cosmetic) |

**Recommended sequence:**
1. **§5 observation period first.** Run one real feature through the current framework on Opus 4.8.
   Log every place the model strains against, or is slowed by, a prescriptive rail. This is the
   evidence base — we de-restrict off *this*, not off §2's benchmarks.
2. **3.1 de-restriction**, driven by that log. Likely start with one skill end-to-end (kbuild or
   kdesign) as the pattern, then propagate.
3. **3.5 calibration rule** — can land in parallel, independent.
4. **3.2 / mechanical-enforcement** — after the pattern is proven.

---

## 7. Open questions (post-decision)

1. **Observation vehicle — DECIDED: CashFlow Pro** (active work, Opus 4.8). It is the project
   that generated the kdesign-kplan-improvements INTENT, so there is prior framework experience to
   compare against, and it carries real E2E stakes. Observation is *live and ongoing* as Karl
   builds — not a manufactured run. Signal captured in `strain-log.md` (this directory).
2. **Strain-log format — DECIDED: light structured template** (see `strain-log.md`). Each entry:
   what the model did/wanted, which rail was involved, the category (forced-suboptimal /
   worked-around / would-do-better-free), and a one-line "what to relax." Capture in the moment;
   we synthesize into de-restriction edits once there's enough signal.
3. **Mechanical enforcement — decouple now or later?** (3.3) Graduate a duplication/layering check
   into `quality-gates` + `kinfra init` independent of the karchitect track, or leave it bundled
   in exploration?
4. **Effort levels in skills** (3.5) — can a skill *declare* its effort (frontmatter?), or only
   recommend it in prose for a human/harness to set? Needs a quick check of harness capability.
5. **Gap-hunting and self-flagged uncertainty** (carried over) — should kdesign's validation
   *explicitly ask* "what are you least sure about?" as a first-class output? Note: per 3.3 this
   *complements* adversarial review, it does not replace it.

---

## 8. Decisions log (2026-05-28)

Recorded from Karl's review of the first draft — the build→design feedback loop in practice:

1. **Optimize for quality, not cost.** The de-restriction thesis is about not stifling a capable
   model, *not* about saving tokens. Token reduction is an incidental side effect, never the goal.
2. **karchitect is separated.** It has never been used; it is pure exploration. It does not
   constrain production-framework evolution and is tracked independently.
3. **Adversarial review stays at full strength.** Rationale: 4.6/4.7 were also sold as "more
   honest"; adversarial review kept paying off regardless. We do not weaken verification on the
   strength of a vendor honesty benchmark. (Lux's first-draft position here was walked back.)
4. **Handoff reframe dropped** as cosmetic.
5. **Observation-first is the method, emphatically.** Gather our own evidence on a real feature
   before de-restricting. §5 is the spine of the plan.
6. **Observation vehicle = CashFlow Pro** (active work). Live, ongoing capture in `strain-log.md`,
   not a manufactured run.

### Applied 2026-05-28 (uncommitted, pending Karl's diff review)

The de-restriction principle (§3.1) was applied to the three core pipeline skills, folding in the
`kdesign-kplan-improvements` initiative for kdesign/kplan (to avoid a double rewrite):

- **kbuild → v0.2.0** (188 → 144 lines). Pure de-restriction. Prescriptive steps → goal-framing;
  scar-tissue `DO NOT`s → reasoned contracts; E2E-honesty contract *strengthened*. Change-map:
  `kbuild-derestricted.md`.
- **kdesign → v0.2.0** (139 → 137 lines, net flat). De-restriction offset by added content: JTBDs
  as first-class artifact (improvement 2.1), implementation-readiness check (2.2), command-query
  gap lens (2.3).
- **kplan → v0.2.0** (148 → 152 lines, grew). Little herding to strip; folded in JTBD↔milestone↔E2E
  traceability with the recipe-as-capability-block caveat (3.1), human-action callouts with the
  compose-vs-sandbox correction (3.2), just-in-time planning depth (3.3), dependency-direction
  consistency check (3.4).

- **kissue → v0.2.0**. Small de-restriction: the over-prescribed "Research" section (4 numbered
  steps + mandated summary) → goal-framing consistent with kbuild. Otherwise unchanged.
- **kreview → left at v0.1.0, deliberately.** Its bulk is review *heuristics* (IMPLEMENT/PUSH-BACK/
  DISCUSS criteria, by-comment-type judgment) — accumulated domain knowledge a capable model
  benefits from, not method-restriction. De-restricting it would stifle quality. Knowing when not
  to cut is part of the principle.
- **`rules/effort-and-model-calibration.md` → new** (§3.5). xhigh for heavy reasoning skills, high
  for linear ones, tier models down only for scoped subtasks; honest that effort is a
  runtime/harness control a skill can only recommend.
- **Held: kworktree, kinfra-onboard.** The heavy infra skills drive real infra state; per
  observation-first, they wait for CashFlow evidence that the principle is safe before any rewrite.

Line count is not the metric — kbuild shrank (over-prescribed), kplan grew (gained real content),
kreview didn't move (already well-calibrated). These skills are now what CashFlow Pro exercises;
the strain-log captures where they chafe. Open-question defaults chosen from CashFlow-proven
practice: JTBDs live in DESIGN.md; coverage is a table per VALIDATION task; readiness checklist is
fixed (not project-type-aware).

---

## 9. Sources

- [Claude Opus 4.8 — Anthropic](https://www.anthropic.com/claude/opus)
- [Anthropic Launches Claude Opus 4.8 With Gains in Coding and Honesty — MacRumors](https://www.macrumors.com/2026/05/28/anthropic-claude-opus-4-8/)
- [Claude Opus 4.8: Benchmarks, Effort & Dynamic Workflows — DigitalApplied](https://www.digitalapplied.com/blog/claude-opus-4-8-release-dynamic-workflows-2026)
- [Skill authoring best practices — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Skill Authoring Patterns from Anthropic's Best Practices — GenerativeProgrammer](https://generativeprogrammer.com/p/skill-authoring-patterns-from-anthropics)
- [Orchestrate teams of Claude Code sessions — Claude Code Docs](https://code.claude.com/docs/en/agent-teams)
- [The Code Agent Orchestra — Addy Osmani](https://addyosmani.com/blog/code-agent-orchestra/)
- [Context windows — Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/context-windows)
- [Managing Claude Code's 1M Context Window: A Practical Guide — Medium](https://medium.com/agentic-builders/managing-claude-codes-1m-context-window-a-practical-guide-8480b49c9fd5)
</content>
</invoke>
