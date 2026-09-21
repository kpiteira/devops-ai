# Review loop runtime

**Status:** planning
**Signed off:** 2026-09-13 — Karl (A1–A9 confirmed one by one in the walkthrough; A9 confirmed as a restatement of the per-run budget, not a new cap; scratch repository created the same day)

## Intent

The PR review loop is two skills of prose — `kbabysit` (486 lines) driving `kreview`
(464) — and most of those lines are shell a model re-derives every round: fetch reviews
and threads, parse Copilot's suppressed comments, compute provenance, poll, reply,
resolve, file issues, count rounds, render the report. Every such line is a place a run
can walk past a rule (#61: 20 of 25 paid reviews on #49 and #51 ran outside every rule
on the page), and every round spends the model's tool calls and tokens on polling and
parsing instead of judgement. This feature moves the deterministic half into a console
script, `kreview`, so the model's part of a round is judgement only: read one packet,
decide dispositions, implement fixes, hand the decisions back. The stop rules signed in
#34 and #61 become code evaluated from data, the loop's state lives in the PR, and the
two skills shrink to the judgement and the guardrails they exist for.

## Outcomes

- `kreview status <pr>` reports every fact the babysit preflight and the re-entry check
  need — PR state, `## Review scope` presence, CI, prior Copilot reviews and their
  effort levels, the provenance boundary, the unreviewed commits, whether a report is
  posted — and a mechanical verdict: ready, or the rule that stops the run.
- `kreview round <pr>` returns one **round packet** in one call: every new finding
  (review threads, Copilot's suppressed comments) with computed provenance, prior
  replies and repeat candidates, the issue comments, the reviewers' summaries and effort
  levels, and the mechanical signals (second-order, no new findings, CI). The model
  reads the packet; it never calls `gh` or `git` to see a review.
- `kreview apply <pr> --dispositions <file>` takes the model's decisions and does the
  rest: replies in each thread, resolves, files one issue per out-of-scope `root_cause`
  class (never one per finding — that is J6's rule and the M2 Surface's),
  records the round in the PR, and decides — continue, or stop with the rule that
  fired. With `--next` it requests the next review, waits for it, and returns the next
  packet, so a round costs the model one `apply --next` call beyond its own fix work.
- `kreview report <pr>` renders the babysit report from the recorded rounds — the
  model supplies the TL;DR and the *what changed* lines, nothing else — and posts it.
- The loop's state (rounds, findings, dispositions, stop) lives in the PR's babysit
  comment. Any session can re-enter with `kreview status` under the same rules and the
  same ledger. Nothing is kept on local disk.
- The `kbabysit` and `kreview` skills contain no `gh` or `git` command: the judgement
  rubric, the loop procedure, the guardrails. Enforced by
  `tests/acceptance/review_loop_runtime/test_m2_the_loop.py::test_skills_contain_no_gh_or_git_commands`
  (J10) — an acceptance test, not an architecture test, so `make check` does not run it;
  it is blocking for M2.
- Measured at feature close, not by a test: tool calls and model tokens per paid round,
  from the `kbabysit` fork transcripts of #63 (before) against the first two PRs
  babysat with the tool (after).

## Invariants

- Every rule signed in #34 and #61 holds unchanged: a written review scope is required
  and never inferred; scope is decided before truth; provenance is three-state and an
  unknown never fires the second-order stop; a suppressed comment is a line-anchored
  finding; a systemic root cause the seat may not fix (pinned Surface) stops the loop
  as the human's decision; the loop stops when it has converged or is diverging and
  on nothing else — no budget unless the human gives one (2026-09-20); re-entry
  re-applies every rule; the loop never merges, never requests a Claude review, never
  force-pushes.
- The tool never commits, pushes, or modifies the working tree, the index, or any
  branch. It reads git and fetches refs, nothing more.
- No token is materialized: GitHub access goes through the authenticated `gh` CLI (D1);
  no secret value appears in any output.
- No new entry in `[project.dependencies]`.
- The skills' judgement text — the assessment tables, isolated/systemic, the four
  dispositions and their definitions, the report's semantics — is moved, not rewritten:
  those are the words Karl signed.
- `kbabysit` runs on an Opus-grade model. Per the 2026-09-14 (M2) amendment below this
  is no longer a frontmatter pin: the loop runs in the Opus agent-deck session that
  invokes it, and preflight states the model and stops on the wrong one. The gate in
  `tests/architecture/test_v2_contract.py` still asserts the old pin and is in
  `make check`, so M2 moves it with the mechanism — the obligation is pinned in the M2
  brief, which is where the executor reads it.

## Non-goals

- A tool-driven loop (`kreview run` calling a model per round). Karl's decision
  2026-09-13: model-driven first, delegating as much as possible to the command;
  revisit after the close measurement.
- Changing what a disposition means or how judgement is made. Copilot's effort level
  (the repository's Copilot code-review setting, or a per-request choice in the GitHub
  UI — either way the human's, and neither reachable from `gh`).
- Reviewer formats other than Copilot's and a human's; hosts other than GitHub.
- `kselfreview` is unchanged; the tool prints the range it is invoked with.
- The observer seat's other jobs (`kobserve launch`/`verify`/`land`).

## Discovered context

- Measured 2026-09-13 on the real PRs, which the acceptance tests use as fixtures
  (`refs/pull/<n>/head` persists after merge, so history is a fixture): #49 has 13
  Copilot reviews, all `Lite`, 15 suppressed findings declared and parsed, 4 threads
  (all resolved, 3 outdated), 13 issue comments; its boundary is `5a9b106` (first
  review, an ancestor of the head `06af8a4`); the two suppressed findings of the
  14:27:15Z review (id 5191010581, `azurekeyvault.py:245` and `:160`) blame at that
  review's commit `70a8f10` to `23ee88a2` and `63465ed7`, both descendants of the
  boundary — a second-order round. #27 has 14 Copilot reviews, boundary `84197e4`
  (ancestor of head `8fbb0be`), 26 threads.
- A thread's `line` is `null` once it is outdated; `originalLine` and
  `originalCommit` are the anchors that survive, and blame runs at that commit.
- Copilot's review body has two formats. Up to 2026-09-14 (v1, every fixture PR): a
  headline, one summary sentence, and `<details>` blocks (*Pull request overview*,
  *File summaries*, *Review details*); the suppressed section and the footer
  (`**Files reviewed:**`, `**Comments generated:**`, `**Review effort level:**`) live
  inside *Review details*. From 2026-09-20 (v2, first seen on #66 review 5260930892):
  a `<!-- ccr-overview-v2 -->` marker, `**Review effort:**` as a header line, no
  suppressed section, and `Open`/`Resolved since last review` lists of the threads.
  M1's brief defines both. Copilot never submits an `APPROVED` review: its approval
  is a `COMMENTED` review whose headline reads *Approval recommended*.
- The kbabysit fork sees no conversation history — a packet must be self-contained.
- Precedent: `ksecret` is the package's second console script
  (`src/devops_ai/cli/ksecret.py`, typer, `_emit` writes UTF-8 bytes); a new script
  needs `uv tool install -e . --reinstall` once, which the README's Secrets section
  says for `ksecret`. The project has no sandbox and no structural-invariants gate
  file of its own (`tests/architecture/` holds the v2 contract, docs hygiene, and
  secret-providers gates); `make check` is quality + unit + architecture tests.
- The contract-integrity guard protects `tests/acceptance/**` and
  `docs/specs/*/briefs/*.md`; the feature's test directory is
  `tests/acceptance/review_loop_runtime/` (importable name).

## Decomposition

| Milestone | Brief | Jobs | Depends on | Status | Evidence |
|-----------|-------|------|------------|--------|----------|
| M1 — read side: status and the round packet | briefs/M1-read-side.md | J1, J2, J3, J4 | — | pending | — |
| M2 — the loop: request, wait, apply, state, report | briefs/M2-the-loop.md | J5, J6, J7, J8, J9, J10 | M1 | pending | — |

## Decisions

- **D1** — GitHub is reached through the authenticated `gh` CLI as a subprocess, git
  through the `git` binary; both are the seams unit tests fake. *Rejected:* HTTP with a
  token read from the environment — materializes a token the tool then owns; and
  GitHub's GraphQL `blame` plus the compare endpoint for ancestry, which would work
  without a clone at two API calls per finding — revisit if the clone requirement bites.
- **D2** — The console script is named `kreview`, the same name as the skill that keeps
  the judgement (Karl, 2026-09-13). Skill text always writes the subcommand form
  (`kreview round`, `kreview apply`) so a model reading it runs a command, not a skill.
  *Rejected:* `kpr`/`kloop` — a second name for one job.
- **D3** — Finding ids are stable and derived from GitHub ids: `t<id>` (the thread's
  first review comment), `s<review-id>-<n>` (nth suppressed entry of that review),
  `c<id>` (issue comment). *Rejected:* per-round sequence numbers — not stable across
  re-entries.
- **D4** — Loop state is a JSON block in an HTML comment at the end of the PR's babysit
  report comment, created at the first `apply` and rewritten every round. *Rejected:* a
  local file — invisible to the observer and to a re-entry from another machine;
  contradicts the contract's durable-state rule.
- **D5** — The tool never pushes. An IMPLEMENT disposition names the fix commit, and
  `apply` refuses a commit that is not on the PR head. *Rejected:* the tool committing
  and pushing on the model's behalf — the fix is the model's work and its commit
  message is where a suppressed finding's trail lives.
- **D6** — Copilot-specific parsing (suppressed section, effort footer, headline) is
  confined to one adapter; everything else is reviewer-agnostic. *Rejected:* treating
  every reviewer body as Copilot's.
- **D7** — Replay flags (`--since`, `--until`, `--include-resolved`, `--dry-run`) make
  a PR's history a fixture, so the stop rules are exercised end to end on real data
  without buying a review. *Rejected:* recorded API fixtures only — those test the
  parser, not the backend.
- **D8** — Every stop rule is evaluated by the tool from data plus the model's tags
  (`shape`, `root_cause`, `on_pinned_surface`, `repeat_of`, verdicts); the model can
  add a stop reason (`--stop`) but cannot remove one.

<!-- A1–A9 were drafted as Assumptions and confirmed by Karl one by one on
2026-09-13. IDs kept — the briefs and tests reference them. -->


- **A1** — The name collision is accepted as D2 describes: skill `kreview` (judgement),
  command `kreview` (mechanics), subcommand form everywhere in skill text.
- **A2** — The write-side acceptance tests run against a scratch repository Karl
  creates, named by `KREVIEW_ACCEPTANCE_REPO` — `kpiteira/kreview-scratch`,
  private, Copilot automatic review **off**, Issues enabled, created 2026-09-13. The tests open and close
  their own PRs and issues there. They skip when the variable is unset; M2 is not
  delivered on skips. **Prerequisite for M2 — met 2026-09-13.**
- **A3** — Exactly one test buys a Copilot review (the request-and-wait path). It is
  gated by `KREVIEW_ACCEPTANCE_PAID=1`, run once by the executor at PR time and once by
  the observer at verify, at Lite cost ($0.05–1 per GitHub's estimate). Every other
  test posts human review comments through the API and costs nothing.
- **A4** — The loop stays model-driven and the tool never calls a model (Karl's answer
  2 on 2026-09-13).
- **A5** — The cut is two milestones: M1 read side, M2 the loop. M2 is the larger
  brief; it can be split at sign-off if Karl wants smaller executor bites.
- **A6** *(narrowed 2026-09-20 — Amendments)* — Every DISCUSS disposition stops the loop (escalate). kbabysit 0.4.0 says
  "DISCUSS items that block merge-readiness"; the tool cannot judge "block", and a
  DISCUSS is by definition the human's.
- **A7** — `apply` refuses to post on a merged or closed PR; `--dry-run` is the replay
  path on history.
- **A8** — The babysit report comment is created at the first `apply` (status *in
  progress*, rounds so far) and rewritten each round, so the observer sees rounds as
  they happen; `report` finalizes it. Before this feature the comment appeared only at the end.
- **A9** *(superseded 2026-09-20 — Amendments)* — Budget default 3 rounds per run, `--max-rounds` raises it; a re-entry is a
  new run with a fresh budget and the inherited ledger (no cumulative cap — #61 item 7).

## Assumptions

<!-- Empty: all nine promoted above on 2026-09-13. -->

## Amendments

<!-- Append-only after sign-off. -->

- [x] 2026-09-13 (M1) decision-change: `kreview status` gains a `ci-failing` verdict,
  last in the order, exit 3 — a red check on the head stops the run instead of being a
  fact the model reads past. Raised by Copilot on PR #66 (twice; the second time as a
  systemic finding on pinned Surface, which stopped the babysit). Graded in M2's scratch
  repository together with `draft` and `scope-empty` (M1 brief D15, M2 Blocking).
  *Rejected:* keeping CI red as a fact plus the skill's "fix CI first" sentence.
  Decided and acknowledged by Karl 2026-09-13.
- [x] 2026-09-20 (M2) decision-change, D14: the loop stops when it has converged or is diverging, on nothing else. No default round budget (`--max-rounds` is opt-in; A9 superseded); a `systemic` root cause seen a second time is the model's class fix or one issue, not a stop (`systemic-repeat` removed), and a third occurrence is `diverging: systemic-third-time`; two consecutive rounds with no fewer findings on the original diff is `diverging: no-progress`; `DISCUSS` is only for a decision the human owns (A6 narrowed) and `on_pinned_surface` means "this seat may not change it"; `apply` persists the stop it decides (`report` changes no state). *Rejected:* keeping the 2026-09-13 table — six paid rounds on #66 stopped four times on rules that ended nothing. Decided by Karl 2026-09-20 ("if it's not converged - and not diverging - we don't stop"; "systemic issues must be researched and fixed by the agent systematically"), acknowledged the same moment.
- [x] 2026-09-20 (M2) decision-change: `kreview report` refuses a running loop (exit 5, both forms); the `manual` stop reason is gone. A report with no stop reached the verdict rule's `else ✅` while the rule's own next sentence said ✅ follows a `converged` stop and nothing else (#66 run 6, Copilot). *Rejected:* a non-✅ verdict for a manual report — it keeps a mid-loop report as a supported path, and a mid-loop report is what the 2026-09-14 trust incidents were. Decided by Karl 2026-09-20 ("I agree with the first"), acknowledged the same moment.
- [x] 2026-09-20 (M1) decision-change: the round packet reads both Copilot body formats, keyed on the `<!-- ccr-overview-v2 -->` marker: `reviews[].format`, `effort` from either effort line, `summary` stripped of both formats' furniture, `suppressed_check` `{0, 0}` on a v2 window; blocking tests on #66's own v1 (round 4) and v2 (round 5) reviews. Found by #66 run 6: Copilot changed its format on 2026-09-20 and every fixture is v1, so M1's tests would have stayed green over a tool blind on its first real round. *Rejected:* mapping `Open`/`Resolved since last review` onto `suppressed` — different concept, and the threads they list are findings already. Decided by Karl 2026-09-20 ("amend m1"), acknowledged the same moment.
- [x] 2026-09-14 (M2) decision-change: `kbabysit` drops `context: fork` + `model:` from its frontmatter; the loop runs in the Opus agent-deck session that invokes it, and preflight states the model and stops on the wrong one. J10's grader asserts the absence of the fork and the presence of the check instead of the pin. *Rejected:* keeping the fork — it hid every round in a sidechain transcript (measured on #72 and #66). Decided by Karl 2026-09-14 ("drop the fork"), acknowledged the same moment.
