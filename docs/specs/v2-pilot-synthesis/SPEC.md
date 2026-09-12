# v2 pilot synthesis — contract v7

**Status:** in progress
**Signed off:** 2026-09-12, Karl — decisions T1–T5 and assumptions A1–A4 confirmed item by item

## Intent

The v2 Human–Model Contract ran end to end once (khealth "challenges", 2026-09-01 →
2026-09-11, `docs/designs/v2-contract/PILOT.md`). The log's 45 rows say what held and
what leaked. This feature turns them into the next revision: the contract text, the rules
loaded as instructions, the planner, executor and babysit skills with their templates, a
new skill for the seat the pilot ran without one, and four kinfra fixes. After it lands,
the next feature planned on this machine runs under a contract that has closed every hole
the pilot found, with each new obligation attached to an artifact or gate that already
exists rather than to anyone's discipline. The synthesis itself is
`docs/designs/v2-contract/REVIEW.md`.

## Outcomes

- `CONTRACT.md` is v7: the escalation bar names product semantics; the grading line is
  stated (deterministic tests define delivered, unpinned product semantics reach the human
  through the PR before merge); the fact-correction path exists; labeled integration-level
  blocking tests are legal; independent verification before merge is named; the observer
  seat is named; the open questions carry the pilot's evidence.
- Rules say the same: `outcome-contracts` (fact-correction path, PR sections, amendment
  split), `test-quality` (acceptance-test checklist), `testing-taxonomy` (labeled
  integration-level acceptance), `quality-gates` (a session owns the review rounds of every
  PR it opens), `effort-and-model-calibration` (model self-check at session start and after
  any restart).
- kspec: interview separates framework semantics from instance configuration; tests are
  drafted before the sign-off walkthrough; the walkthrough carries a per-brief "what the
  tests pin" list; sign-off is a per-item yes; every "passes/fails on main" claim is
  measured and recorded; preflight against the executor's runtime; no infrastructure wired
  into a project PR without a labeled directive; close is two-pass when drift is found,
  promotes tests by kind, sweeps references before archiving, and has a home for notes
  outside the outcomes.
- Templates: the work brief gains a Working environment section, Surface completeness
  prompts, a failure-path prompt, a Measured-on-main column, and the decision-plus-
  rejected-alternative format; the intent spec's amendment log distinguishes pre-checked
  fact-corrections from blocking decision and outcome changes; the close report gains
  promotion-by-kind and Outside the outcomes.
- kbuild: PR body carries three mandatory sections — Decisions I made alone, For the
  human, Facts I corrected; the pre-PR fresh-context review is a named step whose claims
  are measured; the fact-correction path is stated next to the escape valve.
- kbabysit and kreview: a session owns its PR's rounds until merge-ready or explicit
  hand-off; fixes are cited by content after a rebase and every handled thread resolved.
- A new skill, `kobserve`, is the observer seat: launch an executor (explicit agent-deck
  group, model verified, no attribution trailers in kickoffs, never sharing a checkout with
  a child), verify a delivery (independent blocking re-run at the same head, the For the
  human gate put to Karl before merge), land it (spec row on main via a temporary
  worktree, teardown).
- kinfra: `done` removes the slot's volumes; `impl --session` takes `--group`; `sandbox
  rebuild` reuses materialised secrets unless `--refresh-secrets`; the guard labels its own
  paths correctly.
- `tests/architecture/test_v2_contract.py` pins every shape above that is text.
- `EVOLUTIONS.md` item 1 reads pilot complete, v7; guard hardening (required status check)
  is a filed issue.

## Invariants

- The escape valve stays verbatim in the brief template and kbuild.
- Acceptance tests stay writable only on `spec/*` and `replan/*`; the guard's protected set
  does not shrink.
- No new artifact beyond `kobserve` and `REVIEW.md`; briefs, specs and PRs carry the new
  obligations as sections, not as new files.
- Secrets: never printed, never partially masked, never in argv. The rebuild path reads the
  materialised file; it does not echo it.
- `make check` stays green at every commit.

## Non-goals

- Wiring the independent re-run into CI (EVOLUTIONS #5).
- 1Password announce-before-wait and single-approval resolution: routed to the in-flight
  `secret-providers` feature, which replaces the resolver — a note Karl carries into that
  spec; this session does not touch that branch.
- agent-deck's group cap, blocking `session send`, and model loss on restart: third-party;
  workaround notes only.
- Guard hardening via GitHub rulesets: filed as devops-ai #28 by this session.
- khealth product items (`BACKEND_URL` default, per-slot notifier destination, scope
  picker): khealth's; listed in `REVIEW.md` for Karl, not filed by this session.
- A mechanical spec↔test lint: not machine-definable in general; the spec PR review is the
  event that catches it.

## Discovered context

- kworktree's Implementation workflow tells sessions to run `kinfra impl --no-session`
  then `agent-deck add --parent`, which is exactly the launch that inherited a capped group
  on 2026-09-06. `kinfra impl --session` already passes `-g dev`.
- The agent-deck skill lives outside this repo (`~/.claude/skills/agent-deck/`), so its
  workaround notes go in `kobserve`.
- `secret-providers` (branch `spec/secret-providers`, A1–A8 confirmed, unsigned) keeps
  `.env.secrets` residency unchanged, so a rebuild path that reuses that file survives it.
- Before this feature the guard printed "Planner-owned contract file changed" for
  `.github/workflows/ci.yml` and its own script, which are guard paths, not contract
  paths; it now prints "Contract guard file changed" for those.
- The pilot briefs already carried a Working environment section the template lacks.

## Decomposition

Executed in this planning session (decision T4); rows are cross-session state only.

| Area | Status | Evidence |
|------|--------|----------|
| Architecture tests pinning the new shapes | PR | devops-ai #27 — `uv run pytest tests/architecture` → 17 passed |
| CONTRACT.md v7 + rules | PR | devops-ai #27 |
| kspec skill + templates | PR | devops-ai #27 |
| kbuild + kbabysit + kreview + kworktree | PR | devops-ai #27 |
| kobserve skill | PR | devops-ai #27 |
| kinfra: done volumes, --group, rebuild reuse, guard labels | PR | devops-ai #27 — `make check` → unit 337 passed; `uv run pytest tests/integration/test_sandbox_secrets_reuse.py` → 6 passed |
| README, EVOLUTIONS, issue | PR | devops-ai #27; guard hardening filed as devops-ai #28 |

## Decisions

Each with the rejected alternative.

- **T1 — Fact corrections.** An executor may proceed when a requirement is unambiguous and
  only an annotation is false, recording it under *Facts I corrected*; the planner amends
  the spec at PR review. Amendments split: fact-corrections are logged pre-checked and do
  not block; decision and outcome changes block until acknowledged. *Rejected:* every false
  fact a divergence (days for an annotation); executor stops and the planner fixes same-day
  (an executor idles on every annotation).
- **T2 — Blocking-test level.** An integration-level blocking test is legal when the live
  stack cannot exercise the job, labeled with the reason and its measured baseline.
  *Rejected:* strict E2E (M3 would have needed an entra-mode sandbox); per-test human
  directive (ceremony for a label the human already sees at sign-off).
- **T3 — Observer seat.** Its own short skill, named `kobserve` after the log's own word
  for the seat. *Rejected:* notes spread over three skills; folding the merge side into
  kbabysit.
- **T4 — Who edits.** This session, one PR, no briefs; the kinfra fixes ride in that PR as
  their own commit. *Rejected:* executor milestones (stranger test of the contract, more
  ceremony); contract here and the rest by executors.
- **T5 — Guard hardening.** An issue; only the annotation mislabel is fixed here.
  *Rejected:* kinfra prints the ruleset step; a `kinfra guard protect` command via `gh`.
- **Escalated consequences.** An executor's *For the human* item is put to Karl before
  merge as a decision: fix now (replan) or defer to close. *Rejected:* corrective test
  before merge always (the log's 09-10 lesson) — 09-11 shows deferral was his call and
  correct.
- **Rebuild default.** `kinfra sandbox rebuild` and `start` reuse the slot's materialised
  secrets when present and say so; `--refresh-secrets` re-resolves. *Rejected:* always
  re-resolve (an executor waits on a human's keychain); a separate `--offline` flag (two
  names for one behaviour).
- **Impl-branch force-push permission rule.** Declined. kbabysit forbids force-push in the
  loop for a reason; the trigger was a house gate the Working environment section now
  surfaces up front.

## Assumptions

<!-- none — A1–A4 confirmed 2026-09-12 and promoted into Decisions (T3, T4) and Non-goals -->

## Amendments

<!-- none -->
