# v2 pilot — post-pilot review

*Synthesis of `PILOT.md` (45 rows, 2026-09-01 → 2026-09-11, khealth "challenges").
This is CONTRACT.md next-step 8. Input: the log only. Output: what held, what the log
implies changing, where the implications contradict the contract, and which rows are
tooling rather than contract. Rows are cited by date and session as they appear in the log.*

## The watch-list, answered

| Watched | Verdict from the log |
|---------|----------------------|
| Interruptions | M1: zero during the executor run (09-03). Across the pilot the human-typed interventions were: one force-push (09-03), merges (by design), sign-offs, and the 1Password approval that never showed (09-01). Every non-merge interruption traced to tooling, not contract. |
| Escalation quality | Options-first held when it ran. The misses were the *other* direction: product semantics decided by models without reaching him — "silence is a miss" (09-03 post-merge), `last_prompt_at` issued-vs-delivered (09-03), three semantics by the Opus replan (09-04), "morning" (09-08). The models' sense of "consequential" under-weights *what a user-visible state means*. |
| Brief quality | Briefs stayed outcome-only. Gaps were **completeness**, not leakage: a field pinned in M1 but defined in M2 (09-03), the token UI not named as Surface when scopes were added (09-04), the ingestion seam's semantics recovered by inference (09-08), no failure-path line for a send (09-11). One mild leak: a mechanism in M2's Context landed as a change to shared scheduler infrastructure (09-08). |
| Grading | Deterministic tests defined "delivered" correctly every time. The concrete judgment cases (seam semantics 09-01, issued-vs-delivered 09-03, silence-is-a-miss 09-03, morning 09-08) were all *product semantics the grader was indifferent to*. Line to draw: tests grade delivery; product semantics the tests don't pin flow to the human through the PR, before merge. |
| Guard friction | Zero false positives. It was not deployed in khealth until 09-05 (#213); manual runs bridged the gap. Copilot found the CI step is deletable by a PR and the annotation mislabels its own paths (09-05). |
| kinfra fit | Two v1/v2 layout drifts fixed on day one (#24). Recurring: 1Password approval silent and per-process (09-01, 09-08, 09-11); `done` leaves volumes (09-06); no non-interactive rebuild from materialised secrets (09-08); agent-deck group handling (09-06, 09-08). |
| Adversarial test | Earned its place: the first close found real drift (a challenge completing with unanswered days, 09-10) that no blocking test ran far enough to see; the second close, from a different angle, found none (09-11). |

## What held — no change

- Investigation before drafting caught the intent dump diverging from code both ways (09-01).
- The correct-the-draft step at sign-off produced five material corrections (09-01).
- Glossary resolved a vocabulary fight that looked semantic (09-01).
- Executor autonomy: 39 min, 250 tool uses, zero interruptions for a 3,000-line milestone (09-03).
- Review-loop cost proportionate: two Copilot rounds per milestone, findings real (09-03, 09-08, 09-10).
- The escape valve fired correctly on an inferred fact (09-06) and the executor did everything in the right order.
- "Measure, don't trust" propagated from planner to executor unprompted (09-11).
- Fresh-session close review, twice (09-10, 09-11).
- Parallel executors from one planner output, no shared files (09-06).

## Implied changes, grouped into outcomes

Each item names the rows, the change, the target file, and the **event it attaches to** —
the contract forbids mechanisms that rely on ongoing discipline, so every new obligation
below is anchored to an artifact or a gate that already exists.

### O1 — The planner pins what the grader grades (kspec + work-brief template + test-quality rule)

| Rows | Finding | Change |
|------|---------|--------|
| 09-01 (spec-PR review), 09-03 (bare array) | Tests asserted things the brief never said (fixture fossil; envelope vs array). | **Rule: if a test asserts it, the Surface states it.** Sign-off card item: for each brief, a "what the tests pin" list the human reads. No mechanical lint — "keys the Decisions forbid" is not machine-definable in general; the spec PR review is the mechanical event. |
| 09-03 (post-merge), 09-03 (`last_prompt_at`), 09-08 ("morning") | Blocking tests passed under both readings of a semantic the human cared about. | **Opposite-reading check** when drafting tests: for each Decision, "would this test pass under the opposite reading?" If yes, the decision is not pinned — pin it or mark it as the human's to decide. |
| 09-03 (`at_risk`) | Field pinned in M1's Surface, defined only in M2's brief. | **Every pinned field is defined in the brief that pins it, or not pinned.** Brief template note; Done-when item. |
| 09-04 (token UI) | Adding a scope made the UI that enumerates scopes Surface, unnamed. | **Surface completeness**: anything that enumerates, renders, or lists the thing a brief adds is Surface. Template prompt in the Surface section. |
| 09-01 (`test-ingest`), 09-08 (replace-vs-append) | Dev-only seams are Surface; their semantics were recovered by inference. | Seams pinned as Surface carry their semantics like any route. Same template prompt. |
| 09-03 (checklist UX shape) | A UX shape pinned as Surface was right *because it was the product intent*, but the brief didn't say so. | When a UX shape is an outcome, the brief labels it **directive — human** with the reason. Existing category, applied. |
| 09-11 (M4, failure path) | The real bug was in the unspecified failure path of a send. | For every external side effect the Surface pins, the brief states what happens when the channel is down. Template prompt. |
| 09-01 (calendar vs met days) | Test authorship surfaced a semantic the interview missed. | **Draft acceptance tests before the sign-off walkthrough**, explicitly; the walkthrough covers what the tests pin (the item above). kspec ordering. |

### O2 — Measured, not asserted: the pre-executor preflight (kspec + brief Blocking table)

| Rows | Finding | Change |
|------|---------|--------|
| 09-01 (replan, ports) | Grader hardcoded `localhost:8080`; sandboxes serve at `8080+slot`. Fixed via full replan ceremony. | Acceptance tests are checked against the **executor's runtime** (sandbox ports, env), not the planner's. |
| 09-01 (pre-spawn) | Red-for-the-right-reason verified against the live sandbox before spawn. | Explicit pre-spawn step; the observed red is recorded in the brief's Blocking table. |
| 09-03, 09-05 | Runner clock/timezone fragility, twice, in new forms. | Standing **clock and timezone** item in the acceptance-test checklist (test-quality rule). |
| 09-06 (M3 diverged) | "Passes against main" was inferred, not measured; the executor diverged on it. | **Every fact in a Blocking table that says passes/fails against main is measured on a running sandbox before sign-off; the brief records the command and output.** Held on first re-test (09-08). Blocking table gains a *Measured on main* column. |
| 09-10 (close review) | No blocking test ran a challenge to its end; drift lived there. | Checklist item: at least one **run-to-the-end scenario per lifecycle** the feature introduces. |
| 09-10 (M3 picker) | A source-substring test fails a correct refactor and passes a broken render. | Checklist item: **UI jobs assert rendered output**, never source substrings. |

### O3 — The executor's channel to the human (kbuild + contract §3 + kbabysit)

| Rows | Finding | Change |
|------|---------|--------|
| 09-03 (report), 09-03 (post-merge), 09-06, 09-08, 09-11 | "Where the brief needed guessing" was the most useful artifact in the run; mandated as "Decisions I made alone", it worked on M2, M3, M4 — each decision with its rejected alternative. | **PR body section, mandatory: "Decisions I made alone"** (each with the rejected alternative) and **"For the human"** (consequences the executor escalates). kbuild delivering section; PR template. |
| 09-03 (post-merge), 09-10 vs 09-11 | "Silence is a miss" reached him three exchanges after merge. Later, an escalated consequence was deferred to close *by him* — the log calls both "not a miss" and "should have become a corrective test before merge". | Reconciled: the **"For the human" section is put to him before merge**, as a decision — fix now (replan) or defer to close. Either answer is his; what was wrong in M1 was that no answer was asked for. Planner never argues the executor's case for a product semantic (his standing view). |
| 09-03 (pre-PR review), 09-11 (measured the reviewer) | Executor's fresh-context self-review found real bugs pre-PR, cheaper than Copilot; M4's executor measured the reviewer's claims. | kbuild: pre-PR fresh-context review is a named step; its claims are measured like any other. |
| 09-04 (#24) | Babysit loop skipped on a non-milestone PR; a real finding sat overnight. | **A session that opens a PR owns its review rounds until merge-ready or explicit hand-off.** quality-gates rule + kbabysit preamble; kspec's spec PR included (the 09-01 spec-PR review paid: three real findings). |
| 09-08 (Copilot threads) | Executor cited pre-rebase SHAs and left threads unresolved. | kreview/kbabysit note: cite fixes by content after a rebase; resolve every handled thread. |

### O4 — Sign-off and planner discipline (kspec + effort-and-model rule)

| Rows | Finding | Change |
|------|---------|--------|
| 09-04 (replan) | Partial reply treated as consent; guard wired into a project PR without a directive. | **Sign-off is a per-item yes; a partial reply reopens the gate.** A planner never wires infrastructure (guard, workflow) into a project PR without a labeled human directive. (Decided by Karl; recorded.) |
| 09-01 (instance vs framework) | Options-first question elicited instance configuration as if it were framework semantics. | Interview guidance: separate "what should the system allow?" from "what do you want for yours?". |
| 09-04, 09-08 (model) | Planner ran on Opus twice: once by carry-over, once after a tmux restart. | **Model self-check**: a kspec session states its model at start and stops if it is not the strongest frontier model; any relaunch re-checks. The rule already says who runs on what; the check attaches it to session start. |
| 09-05 (A9–A12) | Nine decisions recorded with the rejected alternative each. | Amendment and Decisions format: **decision + rejected alternative**. Template. |
| 09-05, 09-11 (F5) | Planner noted a gap outside scope rather than absorbing it. | Close report gains an **"Outside the outcomes"** section (roadmap notes) so they have a home — feeds EVOLUTIONS #4. |
| 09-03, 09-05 (gitleaks), 09-10 (`npm ci`) | Standing gates and toolchain steps were discovered by pushing. | Brief template gains **Working environment**: standing PR gates *and their scope* (history vs tree), every toolchain's setup step, runtime facts (ports, tz). The pilot briefs already carried this section informally. |

### O5 — Close mode (kspec close + close-report template)

| Rows | Finding | Change |
|------|---------|--------|
| 09-10 (close), 09-11 | Drift found → corrective milestone → second fresh close confirms → archive. | **Two-pass close when drift is found**: the spec stays `closing`; archiving waits for a fresh close after correctives merge. |
| 09-10 (M3 close-out) | Tests promoted by kind: e2e / integration / unit. | Close-report disposition column becomes *promote to: e2e / integration / unit / drop*. |
| 09-11 (second close) | Four outside references to the spec path followed the archive; Copilot caught a fifth. | Close checklist: grep the repo for the spec path before archiving. |

### O6 — Contract text (CONTRACT.md v7)

Changes to the rationale itself, each needing Karl's word (see *Tensions* below for the
ones with real trade-offs):

1. **Escalation bar names product semantics** explicitly alongside data models, security,
   external contracts: *what a user-visible state means* is the human's (09-03, 09-04).
2. **The grading line**: deterministic tests define delivered; product semantics the tests
   don't pin reach the human through the PR's "For the human" section before merge (O3).
3. **Fact-correction path** — Tension T1.
4. **Blocking-test level** — Tension T2.
5. **Independent verification before merge**: the pilot added a step the contract doesn't
   name — the blocking command re-run by a stranger (planner or CI) at the same head, and
   the "For the human" gate. Name it; wiring it into CI is EVOLUTIONS #5.
6. **The launch/observer role** — Tension T3.
7. Open questions updated with pilot evidence: escalation bar (models under-weight product
   semantics; addressed by 1–2), non-convergence (never observed; stays unhandled by design).

## Tensions with the contract — Karl's decisions

**T1 — Fact corrections vs the escape valve and the amendment flag.**
Evidence: a one-line port fix cost a branch, an amendment, a PR and a human round-trip
(09-01 replan); M4's executor met a wrong *annotation* on an unambiguous requirement and
built the requirement, recording the wrong annotation, instead of diverging (09-11) — the
log calls it defensible and asks the contract to say so. The contract today: every false
fact fires the valve; the executor never classifies; every amendment blocks the next
milestone until acknowledged.
- (a) Keep as is. Every false fact is a divergence; every spec change is an acknowledged
  amendment. Cost: days for an annotation. Benefit: the executor never classifies anything.
- (b) Executor may proceed when the requirement is unambiguous and only an annotation is
  false, recording it under "Facts I corrected" in the PR; the planner amends the spec at
  PR review. Amendments split: fact-corrections are logged pre-checked (visible, non-
  blocking); decision- and outcome-changes still block. Cost: the executor decides
  "unambiguous", the one power the contract denies it. Mitigation: it is visible in the PR
  before merge, and misfiling is what the close review exists to catch.
- (c) Same split of amendments as (b), but the executor still stops; the planner's triage
  of a fact-correction is a same-day edit on `replan/*` with no human round-trip. Cost: an
  executor session idles on every annotation.

**T2 — Blocking tests are E2E, or labeled integration-level when the live stack cannot
exercise the job.** Evidence: M3's scope guard could not be exercised under the sandbox's
dev auth mode; the replan filed an in-process test over testcontainers Postgres, labeled
honestly, measured on main (09-08). The contract and the testing-taxonomy rule say
acceptance = E2E.
- (a) Strict: E2E only. M3 would have needed an entra-mode sandbox (new kinfra/env work).
- (b) Allow integration-level blocking tests when labeled with the reason and measured;
  the human sees the label at sign-off.
- (c) As (b), but each such test is a labeled human directive in the brief — his explicit
  acceptance of a weaker grader, per test.

**T3 — The launch/observer role.** The contract leaves "how executor sessions are launched"
deliberately unspecified. The pilot's observer accumulated a real recipe: explicit
agent-deck group (09-06), model check after any restart (09-08), no attribution trailers in
kickoffs (09-11), never share a checkout with a child session (09-08), send to busy sessions
from the background (09-08), independent blocking re-run before merge (09-03, 09-08,
09-10), bookkeeping through a temporary worktree.
- (a) Stays unspecified in the contract; the recipe lives in the agent-deck and kworktree
  skills as notes.
- (b) A named role with its own short skill (launch, verify, land) — one more artifact.
- (c) Fold the merge-side steps (independent re-run, "For the human" gate, spec-row
  bookkeeping, teardown) into kbabysit's end state, and the launch-side notes into the
  agent-deck skill.

**T4 — Who edits the skills.** Skills are symlinked; edits take effect for every session
on this machine immediately. Options: (a) this planning session edits contract, rules,
skills and templates directly on the spec branch, one PR, no executor — fastest, but no
stranger reads the brief; (b) executor milestones per lifecycle stage with architecture
tests as the blocking bar — the stranger test of the contract's clarity, more ceremony;
(c) contract + rules here (they are the decisions), skills + templates + kinfra by
executors.

## Tooling, separated from the contract

### kinfra (code under `src/devops_ai/`)

| Rows | Item | Proposal |
|------|------|----------|
| 09-06 | `kinfra done` leaves the slot's named volumes; a stale May volume blocked a launch. | Milestone: `stop_sandbox` runs `down --volumes` (project name is per slot, so only the slot's volumes go). |
| 09-01, 09-08, 09-11 | 1Password approval is silent and per-process; ten `op read` calls, each a prompt, none announced. | Announce *before* resolving ("resolving N secrets via 1Password — approve the prompt"); resolve all refs in **one** `op` process so it is one approval. **Overlap:** the in-flight `secret-providers` spec (`spec/secret-providers`, A1–A8 confirmed, not yet signed) replaces this resolver with `ksecret`'s 1Password provider. Building on the old resolver would be thrown away; the natural home is that feature's 1Password provider. |
| 09-08 | 1Password expired mid-run; the executor waited ~20 h on a human's keychain, then rebuilt by hand from the materialised secrets file. | Milestone: `kinfra sandbox rebuild` reuses the slot's materialised secrets when present; `--refresh-secrets` re-resolves. Stale-secret risk accepted: the file is what the running containers already use. |
| 09-06 | Executors launched outside `kinfra impl --session` inherited a capped agent-deck group. | Milestone: `kinfra impl --session --group <name>` (default `dev`, always passed explicitly). |
| 09-05 | Guard annotation mislabels `.github/workflows/ci.yml` as a contract file. | Fold into the guard-template fix below. |

### Templates and guard

| Rows | Item | Proposal |
|------|------|----------|
| 09-05 | A PR can delete the guard's CI step; real protection is a required status check / ruleset. | **T5 for Karl**: (a) `kinfra init` prints the ruleset instruction (make the guard job a required check) and generates a CODEOWNERS entry for the guard and workflow; (b) a `kinfra guard protect` command that sets the ruleset via `gh api`; (c) an issue, out of this feature. |
| 09-03 | Standing house gates (gitleaks history scan) not visible to the executor. | Covered by O4's Working environment section; kinfra init could also list detected gates into project.md (small). |

### agent-deck (external tool behaviour)

Groups default `max_concurrent=1` and worktree children inherit the parent's group (09-06,
09-08); `session send` blocks on a busy target (09-08); the model setting does not survive
a tmux restart (09-08). Proposal: recipe notes in the agent-deck skill (T3); issues on
agent-deck if Karl wants them fixed at the source.

### khealth (product issues, not this repo)

`BACKEND_URL` defaults to production (09-10); the sandbox notifier delivers to Karl's real
channel — a per-slot test chat is a `[sandbox.env]`/`[sandbox.secrets]` entry in khealth's
infra.toml, not a kinfra feature (09-03); immediate catch-up checklist and double delivery
on create-after-prompt-time (09-04, fixed in replan). Proposal: khealth issues.

### Out of scope

macOS per-app file access blocking the observer's reads (09-08): human-side outage, no
framework change. Scoped permission rule for impl-branch force-push (09-03): declined —
kbabysit forbids force-push during the loop for a reason (orphaned threads), and the
trigger was a house gate the Working environment section now makes visible up front.


## The synthesis PR as its own case (2026-09-12)

devops-ai #27 — this synthesis — ran **13 Copilot review rounds** before Karl stopped it.
The contract, rules, skills and templates converged by round 4; rounds 5–13 landed almost
entirely on `src/devops_ai/`, each on the previous round's fix: volumes on `done` → secrets
reuse → stale slot dir → destructive label cleanup → concurrent `impl` races → registry
locking → locked stale sweep. Every finding was true; together they rewrote the slot
registry's concurrency model inside a prose PR. Karl's verdict: lifting the 3-round cap
after round 3 was right (round 4 was significant); the failures were the loop's, and they
are now rules in kreview (OUT-OF-SCOPE decided first) and kbabysit (measured stop rules).

Per-round data, as the new rules would have read it:

| Round | Threads | Implemented | Findings on earlier review-fix commits | In scope after the fence |
|-------|---------|-------------|----------------------------------------|--------------------------|
| 1 | 3 | 5 | 0 | 5 |
| 2 | 1 | 5 | 1 of 5 | 5 |
| 3 | 3 | 8 | 3 of 9 | 8 |
| 4 (cap lifted) | 0 | 9 | 5 of 10 | 7 |
| 5 | 4 | 7 | 6 of 7 | 1 (the literal-secret leak) |
| 6 | 1 | 5 | 5 of 5 | 0 |
| 7 | 0 | 8 | 8 of 8 | 0 |
| 8–12 | 10 | 17 | all | 0 |
| 13 | 3 | 0 | 3 of 3 | 0 → issue #31 |

- **OUT-OF-SCOPE first** (kreview): from round 5 the in-scope count drops to one, then
  zero. `zero-implement` fires after round 6.
- **`oscillation`** (kbabysit rule 4): round 6 is the first where every finding sits on
  lines introduced by review-fix commits. Fires after round 6.
- **`trend`** (rule 5, window reset at the lift after round 3): raw counts 9 → 7 → 5 fall,
  so on raw numbers it would not have fired before round 7; on fenced counts it is moot,
  `zero-implement` fires first.
- **`cap`** (rule 6): the lift names a number — default 3 + 2 = 5. Fires after round 5.

Under the new rules the loop ends at round 5 (cap) or 6 (oscillation, zero-implement), not
13. The eight extra rounds cost eight Copilot reviews, eight CI runs and the better part of
a day, and produced code that is better than main but belongs in its own scoped change
(the concurrency tail is issue #31).
