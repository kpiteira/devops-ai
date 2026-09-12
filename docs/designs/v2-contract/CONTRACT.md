# devops-ai v2 — The Human–Model Contract

*Design document, September 2026, v7 — revised after the first pilot (`PILOT.md`, synthesis in `REVIEW.md`). Audience: a reader — human or model — with no prior context. Everything is defined at first use; if a sentence here requires knowledge of the conversations that produced it, that sentence is a bug.*

## What this is

devops-ai is a framework for building software where AI models do nearly all planning and implementation, and a single human owns the product. This document specifies the *contract* between three parties:

- **The human** — owns the product: what to build, why, what tradeoffs are acceptable. Does not read or write code.
- **The planner** — the strongest available frontier AI model (today: Claude Fable 5, GPT-5.6 Sol High+), used where judgment matters most: turning the human's intent into an executable plan, writing the tests that define "done", reviewing finished work, teaching the human what he needs to know.
- **The executor** — the strongest cost-effective coding model (today: Claude Opus 5, or GPT-5.6 Terra-class), which implements the plan with real autonomy: it chooses the path, writes the code, and has standing to push back when the plan is wrong.

The contract's core idea: **be rigid about outcomes, silent about paths.** The previous version of devops-ai prescribed process — ordered tasks, steps, files to touch. Frontier models now plan and verify better on their own than when walked through someone else's plan, so prescription wastes exactly the ability being paid for. All rigidity therefore moves into *contracts*: precise definitions of done, enforced automatically — and the path to done belongs to the models.

A second principle governs this document itself: every mechanism must either run automatically or attach to an event that already happens. Nothing may rely on anyone's ongoing discipline. When in doubt, leave it out.

## Units of work

- **Feature** — the unit the human plans at: a coherent piece of product value he decides to build.
- **Milestone** — a subdivision of a feature, and the unit of *delivery*: each milestone is user-visible behavior, demonstrable end-to-end — a vertical slice, never a horizontal layer ("the persistence part"). A milestone that only makes sense as a prerequisite for another milestone is a disguised step: merge them. Vertical slicing is load-bearing; the contract rule below depends on it.
- **Work brief** — the *document* that specifies a milestone, the way a PRD describes a product without being the product. The brief is what an executor session receives; the milestone is what the user receives.
- **Task** — removed from the framework. The path from brief to delivered milestone is the executor's to find.

## The lifecycle of a feature

### 1. Planning

The human starts a session with the planner and provides an **intent dump**: what he wants, why now, constraints, half-formed decisions — in whatever state his thinking is in. Polish is not required; the planner's first job is to extract what's missing.

A planner session confirms it is running on the strongest model before it starts, and again after any restart — the pilot lost a planner to the executor's tier twice, once by carry-over from a previous session and once when a session manager resumed it on its default model.

The planning session proceeds:

1. **Interview, with just-in-time walkthroughs.** The planner questions the human until no material ambiguity remains, and must not fill gaps with assumptions silently. Its questions keep two things apart: what the system should *allow* (framework semantics) and what the human wants for *his* instance (configuration) — the pilot's first interview elicited the second as if it were the first. Whenever a question or decision depends on a region of the codebase, the planner first walks the human through it — what's there, how it's shaped, what has changed since he last looked. Grounding serves the decision in front of him, not a ritual tour at session start. (The walkthroughs are also how the human's understanding of the system stays alive over time; see "How the human keeps up".)
2. **Investigation.** The planner studies the code and the archived specs of past features in the same region, and challenges the feature's scoping if warranted.
3. **Drafting.** The planner writes the **intent spec** (next section), decomposing the feature into milestones, writing one work brief per milestone, and — critically — authoring each milestone's acceptance tests *before* the sign-off walkthrough: writing the tests is the sharpest ambiguity detector the planner has, and what they surface belongs in front of the human, not after him.
4. **Sign-off.** The human corrects the draft and signs it. Anything the planner inferred rather than heard sits in an explicit *Assumptions* section, and an assumption only becomes a decision by the human's word. **Sign-off is a per-item yes**: each assumption, and each brief's list of what its tests pin, is confirmed or corrected; a partial reply reopens the gate; nothing is signed by silence.

### 2. The intent spec

The spec is one page plus work briefs (if the intent won't fit a page, it's probably two features). Its sections: **Intent** (one paragraph: what changes and why — the touchstone for the final review), **Outcomes** (observable end states a stranger could verify), **Invariants** (what must not change), **Non-goals** (an explicit scope fence), **Discovered context** (what the planner's investigation found that an executor won't cheaply rediscover), **Decomposition** (the milestones, dependencies, and per-milestone status — this doubles as progress state across sessions), and **Assumptions**.

**The contract rule — the executor never grades its own work.** Because each milestone is user-visible behavior, the planner can write its end-to-end acceptance tests *at planning time, before any implementation exists* — so nothing about the implementation can leak into the tests. These planner-authored tests are committed alongside the spec and are the milestone's **blocking criteria**: the milestone is delivered when these pre-existing tests pass. The executor writes whatever unit tests it finds useful — those are tools, not contract — and if it believes an acceptance test is *wrong*, that is an escalation, never an edit: acceptance tests are writable only in planning and re-planning sessions. Without this rule, the same agent authors the code, authors the grader, and is driven toward making its own grader pass — a closed loop that measures nothing.

Two consequences the pilot taught. **If a test asserts it, the brief's Surface states it** — a grader that pins more than the brief (the pilot's bare array where the house convention was an envelope) is the planner quietly deciding shape. And **a test that passes under both readings of a decision pins nothing**: for each decision the human cares about, the planner asks whether the test would pass under its opposite, and either pins it or marks it as his to decide. The pilot's "an unlogged day counts as missed" passed every blocking test under both readings and shipped without him.

Acceptance tests are **scoped runs, not general-CI members**: they execute inside the executor's goal loop and as a gate on their own milestone's PR, and nowhere else — end-to-end suites in global CI make CI unbounded, and a not-yet-implemented milestone's tests are *supposed* to be failing. Committed at planning but invoked only in scope, they are inert until their milestone is in play. Whether a delivered milestone's acceptance tests are then promoted into the product's standing e2e suite is the human's call, made at feature close.

#### Anatomy of a work brief

A milestone's outcome is expressed as one or more **jobs-to-be-done (JTBDs)** — structured statements of what a user can accomplish once the milestone is delivered: *when [situation], [who] can [job], so that [value]*. Multiple JTBDs are fine when one vertical slice genuinely completes several jobs, but every JTBD must map to at least one blocking acceptance test — a job with no test is an aspiration, not a contract, and a test with no job is process leaking back in.

> **Brief 3 — Export history** *(milestone status: pending)*
> **Jobs:**
> J1 — When reviewing my finances, a signed-in user can download their full transaction history as CSV, so that they can analyze it in their own tools.
> J2 — When an export is large, the user can see progress and cancel, so that the app never feels hung.
> **Blocking:** `pytest tests/acceptance/test_export.py -q` exits 0 *(planner-authored at planning time; covers J1, J2)*
> **Advisory:** export of 10k rows completes in under 5s locally
> **Invariants:** no new dependencies in `/core`; public API unchanged
> **Non-goals:** no PDF export; no admin bulk-export
> **Context:** the nightly reporting job reads the same query helper; changing its signature breaks reports.

*Blocking* criteria define delivered. *Advisory* criteria are worth attempting but never worth burning a session on.

**Measured, not asserted.** Every claim a Blocking table makes about the current code — "fails on main", "passes on main" — is measured on a running sandbox before sign-off, and the brief records the command and its output. The pilot's one divergence was a planner's inferred "passes against main" that a running stack contradicted. The same preflight checks the tests against the *executor's* runtime — sandbox ports, environment, clock and timezone — not the planner's laptop.

A blocking test is end-to-end against the milestone's pinned Surface. When the live stack cannot exercise a job (the pilot's case: scope enforcement is invisible under the sandbox's dev auth mode), an **integration-level** blocking test is legal, labeled with the reason and its measured baseline, so the human sees at sign-off exactly how strong the grader is.

A brief is **self-contained for everything it pins**: every field it names is defined in that brief, not a later one; anything that enumerates, renders or lists the thing the brief adds is Surface too; a dev-only seam pinned for the tests carries its semantics like any route; and for every external side effect the Surface pins, the brief says what happens when the channel is down — the pilot's last real bug lived in an unspecified failure path. A brief also carries the facts of the **working environment**: the repository's standing PR gates and their scope (a secret scan that reads history, not the tree, changes what a clean first commit means), every toolchain's setup step, and the runtime facts the tests depend on.

Spec language follows a **lint** (a warning, not a law): sentences should be a *fact* about the world, a *decision* already made, or a *testable end state*. A fourth kind is legal but must be labeled — a **directive**, a path deliberately prescribed by the human for reasons outside the codebase ("directive — human: use provider X, contract already signed"). Directives are the human's alone: a model that wants to prescribe a path doesn't get this category — it makes a *decision*, which is challengeable through the escape valve. An unlabeled process instruction ("start by refactoring…") is the smell the lint exists to catch, because unowned process prescription is how the old framework creeps back in.

Every brief also carries the **escape valve**, verbatim in the template: *"If a stated fact is false, a decision conflicts with what's actually in the codebase, or an acceptance test contradicts a job: stop and describe what you found. Don't comply, and don't classify the problem yourself."* Classification needs cross-feature context the executor doesn't have, so triage belongs to the planner.

**Fact corrections** are the one exception. When a requirement is unambiguous and only an annotation about the current code is false (the brief says a path is unchanged for some state; main shows otherwise), the executor builds the requirement and records the correction under *Facts I corrected* in its PR; the observer seat verifies each against the code and amends the spec at verification, before merge. The executor's judgment is confined to "is the requirement unambiguous?" — a false fact that changes what to build is still the escape valve.

### 3. Execution

The executor works one milestone at a time in its own sessions; milestones with no dependency between them may run in parallel, each in its own session. A session's entire context is the work brief and the current code — it does not need, and does not get, the planning conversation. A milestone usually fits one session, but nothing depends on that: all state lives in git (code, PRs, the spec's status fields), so milestones and features span as many sessions as they need.

Each session runs against the milestone's blocking tests using the harness's goal loop (`/goal` in Claude Code: an evaluator re-checks the criteria after each turn and continues the session until they hold), with permissions pre-approved so the loop isn't parked waiting for a human. One guard rail:

**Divergence.** The executor's report is written into the spec's milestone status in git — the same place all cross-session state lives — and triage happens in a planner session (how a given harness launches that session is a skill concern, not specified here). The planner triages: a wrong *fact* is corrected in the spec and work continues; an untenable *decision* triggers a **re-planning pass** — a scoped rerun of planning steps 2–4 for the affected milestones, the only context besides original planning where acceptance tests may be rewritten; a wrong *outcome* (a job itself) goes to the human, because jobs are his and no model quietly renegotiates what the feature is for. Every resolution is written back into the spec, so the next session starts from truth. Amendments accumulate flags on the spec in two kinds: **fact-corrections** are logged pre-checked and block nothing; **decision- and outcome-changes** stay unchecked until the human acknowledges them, and no new milestone starts while one is pending — seconds usually, occasionally the moment he catches a renegotiation he'd have missed. His signature thereby keeps meaning something.

**The executor's channel to the human.** A brief cannot foresee every product semantic an implementation will force. The executor decides what it must to keep moving, and makes every such call visible in the PR body under three mandatory sections: ***Decisions I made alone*** (each with the alternative it rejected), ***For the human*** (consequences it believes are his — product semantics above all: what a user-visible state *means*), and ***Facts I corrected***. Before merge, the **observer seat** (below — a planner-tier session, `kobserve verify`) puts *For the human* to him as a decision — fix now through a re-planning pass, or defer to the feature close — and never argues the executor's case for a product semantic. The deterministic tests define delivered; what they leave unpinned reaches him this way, before merge, rather than three exchanges after.

A finished milestone becomes a PR, gated by the validation pipeline — the planner-authored acceptance tests (run for this PR specifically) and the automated coherence checks (the architecture tests and new-public-symbol detection defined in "How the human keeps up") — by **Independent verification** — the blocking command re-run by a stranger at the PR's head, matching the executor's output; a planner session today, CI once the gate wiring in the evolutions backlog lands — and then by the product's **code review process**, exactly as any PR is today. A session that opens a PR owns its review rounds until the PR is merge-ready or explicitly handed off; the pilot's one unread review round sat on a side PR nobody owned. Who reviews is whatever the product's current arrangement is; today that typically still includes the human, which sits in visible tension with this document's premise and is precisely why evolving code review is its own item in the devops-ai evolutions backlog. This contract neither depends on nor changes it. Integration is progressive — one PR per milestone, merged as it clears review, never a long-lived feature branch accumulating until feature close.

**The observer seat.** Between the human and the planner and executor sessions, someone launches each executor, verifies each delivery and lands each merge. The pilot ran that seat by hand and it accumulated a real recipe (an explicit session group, a model check after any restart, no attribution trailers in kickoffs, never sharing a checkout with a child session, bookkeeping on main through a temporary worktree, teardown). It is now a named seat with its own skill, `kobserve` — launch, verify, land — so a stranger can run it.

Because milestones are vertical slices with machine-run e2e acceptance tests, every merged milestone is *demonstrable on demand*: the human can run or watch the demo of any milestone whenever he wants to ground himself — but this is entirely optional, gates nothing, and the framework must work when it never happens. Validation is the pipeline's job, not his. The intended steady state is: specify the feature, say go, and meet it again when it's done.

### 4. Feature close

When the last milestone has merged, the planner runs one final review in a *fresh* session (no execution context — an agent that wrote the diffs cannot see their drift), with the spec and the whole feature's diff as input. It answers the one question no automated check can: taken together, do the changes satisfy the spec's *intent*, not merely its listed criteria? Output: a short report, plus corrective milestones appended to the spec if drift is found. It is deliberately small, because everything checkable has already been checked per-milestone. When drift is found the feature stays open: the corrective milestones run, and a *second* fresh session confirms before the spec is archived — the pilot's first close found a lifecycle drift no blocking test had run far enough to see, and its second, from a different adversarial angle, found none. The close also decides each acceptance test's fate by kind (promote to the standing e2e, integration or unit suite, or drop) and records what it saw that lies outside the feature's outcomes, so roadmap notes have a home.

## How the human decides

Two failure modes shape this section, both observed in practice. First: a human who no longer reads code gets presented with design choices he can no longer evaluate, approves the model's recommendation by default, and the "decision" is falsely attributed to him. Second: complexity compounds silently until his sign-offs are theater.

**What reaches him.** Whether a choice escalates to the human is judged by the planner on **blast radius and reversibility**: consequential, hard-to-reverse choices — data models, security-relevant behavior, external contracts, **product semantics** (what a user-visible state means: the pilot's "is an unlogged day a miss?"), anything constraining future features — are his; contained, reversible choices belong to the models, however interesting. The pilot showed that models' sense of "consequential" under-weights product semantics in particular, which is why they are named here and why the executor's PR has a section for them. The validation pipeline provides a mechanical assist (a new public symbol or module appearing in a PR diff flags "a concept crossed a boundary" for the planner to consider), but the signal informs the judgment; it doesn't replace it.

**How it reaches him.** Escalations arrive **options-first**: the tension, the options, their consequences — in terms he's been taught. The model gives its recommendation after the human states a leaning, or immediately if he asks. "What do you think?" is legitimate: that's deference made explicit and chosen. What's being prevented is anchoring-by-default, where a fluent recommendation arrives first and half-understood approval follows. If he can't form a leaning at all, that's the signal to be taught before deciding, not to defer silently.

**How the human keeps up**, with no discipline required:

- **Planning walkthroughs** (lifecycle step 1) refresh his model of each code region exactly when he's about to use that understanding. Concepts he learns accumulate in a lightweight glossary — a record and agenda of what he's been taught, not an enforced vocabulary law.
- **On-demand demos.** Any merged milestone is demonstrable whenever he wants contact with the system's actual behavior — pull-based grounding, never an obligation.
- **Architecture-as-tests.** The enforceable half of architecture — dependency direction, module boundaries, "nothing outside /core imports the broker client" — lives as executable rules in CI (the technique is called *architectural fitness functions*; tooling: import-linter or pytest-archon for Python, dependency-cruiser for TypeScript, ArchUnit for JVM). Enforced structure is run, not read, so it can't go stale — and it mechanically blocks local optimization, since "locally better but violates a boundary rule" fails CI instead of requiring anyone's judgment.

**No standalone decision log**, deliberately: they metastasize into point-in-time entries that read as history, not principle. A decision that deserves to outlive its feature is promoted into an artifact that *enforces* it — a spec invariant, an architecture test, a glossary note. The rest expires with the feature; archived specs stay searchable and the planner's investigation phase reads them, so occasional re-litigation is accepted as cheaper than tending a rationale jungle. (An acknowledged tension, watched in the pilot, not a solved problem.)

## Deliberately unspecified

The following are real mechanics, consciously deferred to the templates, skills, and harness configuration rather than omitted by accident: the file format and enforcement of amendment flags; how a PR is mapped to its milestone so the right acceptance tests run; the harness-specific mechanics of launching a session (the *seat* is specified above; the commands are `kobserve`'s); the repo layout for specs, briefs, archived specs, and the glossary; how the goal-loop evaluator is configured per harness; and the mechanics of the adversarial test. A future reader finding one of these unanswered has found a deferral, not a hole.

## Next steps

Steps 1–8 of v6 are done: templates, kspec, kbuild, the validation pipeline, the close review and one full pilot (`PILOT.md`), synthesised in `REVIEW.md` into this revision. What remains:

1. **Wire independent verification into CI** (evolutions backlog #5): the blocking command on a self-hosted or ephemeral stack, required at merge, so the re-run no longer depends on a planner's laptop.
2. **Harden the guard**: a PR can delete the guard's CI step; real protection is a required status check — a repository setting, filed as an issue.
3. **Second pilot** on a different product, watching what v7 introduced: the fact-correction path (does an executor ever misfile a decision as a fact?), the *For the human* gate (does it fire, and before merge?), `kobserve` run by a stranger, and labeled integration-level blocking tests (do they stay the exception?).

<details><summary>v6 next steps, for the record</summary>

1. **Templates:** intent-spec and work-brief skeletons — sections above, JTBD structure, lint stated at top, escape valve baked in. They live in the devops-ai repo and distribute to products.
2. **Planning skill — the successor of kdesign** (planner-targeted): interview flow with just-in-time walkthroughs, Assumptions section, acceptance-test authorship, options-first escalation. Enforces artifact structure, not planning steps. **kplan is deleted**, not rewritten: its job was splitting milestones into tasks, and tasks no longer exist.
3. **kbuild rewrite** (executor skill, thin): consume one brief, run the goal loop on its blocking tests, honor the escape valve, write divergence reports for planner triage.
4. **Strip defensive scaffolding** from existing prompts and CLAUDE.md ("verify your work", "think carefully"); keep outcome constraints; move durable invariants into CLAUDE.md.
5. **Validation pipeline:** add new-public-symbol detection per PR; add the first architecture tests.
6. **Feature-close review:** define the fresh-context planner session — spec and feature diff in, report and corrective milestones out. (How it is invoked by any particular harness is out of scope here.)
7. **Pilot on one real feature.** Measure: interruptions; escalation quality (were the decisions that reached the human actually his?); and the **adversarial test** — a fresh session attempts to make every blocking criterion pass while violating the spec's intent. If it succeeds, the contract layer isn't holding its weight.
8. **Post-pilot review:** did briefs stay outcome-only; did the right things escalate; did any walkthrough concept need re-teaching; did expired rationale get expensively re-litigated?

</details>

## Open questions

- The escalation bar (blast radius + reversibility) is judgment, not a rule. The pilot's answer: for data, security and infrastructure choices the models' sense matched the human's; for product semantics it did not, four times. v7 names product semantics in the bar and gives the executor a channel for them. Whether that closes the gap is what the second pilot watches.
- Non-convergence is currently unhandled by design: nothing stops an execution session that thrashes or starts bending code toward an unreachable test. Fixed budgets were rejected (any static limit halts legitimate long runs far more often than it catches pathology). Five executor runs in the pilot converged honestly; the question stays open, and detection, if ever needed, should key on symptoms, not duration.
- Briefs are growing a checklist (Working environment, failure paths, Surface completeness, measured baselines). Each item is a fact or a testable end state, not a path, so the lint holds — but a brief that reads like a form is a smell worth watching. Artifact volume felt right through one pilot; the second decides whether it still does.
