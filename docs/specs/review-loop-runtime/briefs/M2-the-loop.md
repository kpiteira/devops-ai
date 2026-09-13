---
feature: review-loop-runtime
milestone: M2
spec: ../SPEC.md
blocking: uv run pytest tests/acceptance/review_loop_runtime/test_m2_the_loop.py -q
---

# Brief 2 — The loop: request, wait, apply, state, report

## Jobs

- **J5** — When a round needs a reviewer, the model can run `kreview round <pr>
  --request --wait <s>` (or `apply --next`) and the tool requests the review, waits
  for it, and returns the packet, so that the model never polls.
- **J6** — When the model has decided every finding of a round, it can hand the
  decisions to `kreview apply <pr> --dispositions <file>` and the tool replies in each
  thread, resolves what is handled, files one issue per out-of-scope **class** (findings
  sharing a `root_cause` share one issue — kreview 0.4.0: one issue for the class, never
  one per site), and records the round in the PR, so that the model's only writes are
  its fix commits.
- **J7** — When a round is applied, the tool decides continue or stop from the round's
  data and the model's tags, naming the rule that fired, so that no stop rule depends on
  a model remembering it.
- **J8** — When any session, from any seat, runs `kreview status` on a PR with a
  posted report, it sees the loop's state and the re-entry advice, and `apply` refuses
  to spend a round on a stopped PR without an explicit `--reenter`, so that re-entry
  goes through the rules with the inherited ledger (#61 item 6).
- **J9** — When the loop stops, the model can run `kreview report <pr>` with its
  TL;DR and *what changed* lines and the tool renders and posts the babysit report from
  the recorded rounds, so that every number in the report is computed.
- **J10** — When the model follows the `kbabysit` and `kreview` skills, no step is a
  `gh` or `git` command, so that the skills are judgement and guardrails only.

## Surface

Everything in M1 holds. Additions:

### `kreview round … [--request] [--reviewer LOGIN] [--wait SECONDS]`

- `--request` requests a review from `--reviewer` (default `copilot`, meaning the
  Copilot reviewer as `gh pr edit --add-reviewer @copilot` addresses it) unless a
  submitted review by that reviewer exists for `head_sha` or a request to it is already
  pending; `--reviewer none` requests nobody and only waits (what the free acceptance
  tests use, and `apply --next` honours it). The packet gains `requested: requested |
  already-reviewed | pending | not-requested`.
- `--wait SECONDS` returns as soon as a review is submitted, or a review thread or
  issue comment is created, later than the request time (or than `since` without
  `--request`), else at the deadline. The packet gains `no_show` (true when the deadline
  passed with nothing new) and `elapsed_s`. Polling interval is at most 30 s.
- The packet's `signals` gain `budget: {max_rounds, used_this_run}` and the packet
  gains `ledger: {<finding-id>: {verdict, reply_url, issue}}` for every finding a prior
  round of this PR recorded, so `repeat_candidates` can be read against their
  dispositions.
- `since` now defaults to the last recorded round's `until` from the state block.

### `kreview apply <pr> --dispositions FILE [--next [--wait SECONDS]] [--max-rounds N] [--stop REASON] [--reenter] [--dry-run] [--since ISO] [--until ISO]`

**Dispositions file** (JSON): `{"round_note": <str, optional>, "dispositions": [ … ]}`,
one object per finding and per issue comment the model treats as a finding:

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | always | a finding or comment id from the round's packet |
| `verdict` | always | `IMPLEMENT` \| `PUSH_BACK` \| `DISCUSS` \| `OUT_OF_SCOPE` |
| `shape` | always | `isolated` \| `systemic` |
| `root_cause` | iff `systemic` | one line naming the class |
| `on_pinned_surface` | `systemic` only, default false | the root cause sits on Surface a brief or spec pins |
| `repeat_of` | optional | id of the prior finding this one re-raises (from `ledger`) |
| `commit` | `IMPLEMENT` | the fix commit; must be reachable from the PR head |
| `reply` | `IMPLEMENT`, `PUSH_BACK`, `DISCUSS`; optional for `OUT_OF_SCOPE` | IMPLEMENT: one line on what changed; PUSH_BACK/DISCUSS: the reasoning |
| `scope_outcome` | `OUT_OF_SCOPE` | which review-scope outcome the fix does not serve |
| `issue_title` | `OUT_OF_SCOPE` | the issue's title |

Validation happens before anything is posted; any violation is exit 2 with every
violation on stderr and nothing written: an id not in the round, a round finding with
no disposition, a `systemic` without `root_cause`, an `IMPLEMENT` whose `commit` is not
on the PR head (fetched first), a missing required field, a `verdict` outside the four.
Each violation line names the disposition's `id`, and a commit violation also names the
offending commit — at least its abbreviated sha — so the model can see which one it is
without re-reading its own file.

**Actions**, in this order, per disposition:

- Thread findings get one reply comment in their thread, then are resolved for
  `IMPLEMENT`, `PUSH_BACK`, `OUT_OF_SCOPE`; a `DISCUSS` thread stays open. Reply bodies:
  `IMPLEMENT` → ``Fixed in `<sha>` — <reply>``; `PUSH_BACK` and `DISCUSS` → `<reply>`;
  `OUT_OF_SCOPE` → `Real, but outside this PR's scope (<scope_outcome>) — filed as
  #<issue>.` followed by `<reply>` when given. With `repeat_of`, the body ends with a
  line `Prior: <url>` — the prior finding's reply URL, or its issue URL.
- Suppressed findings and issue comments get no reply; their disposition is recorded in
  the state block and rendered in the report comment.
- `OUT_OF_SCOPE` files one issue in the repository, before its reply, titled
  `issue_title`, body:

  ```
  Raised by <reviewer> on #<pr> (<finding url>), out of that PR's review scope: serves none of <scope_outcome>. Filed rather than fixed there.

  <finding body, verbatim>
  ```

  Reviewer text never passes through a shell. Two findings with the same `root_cause`
  and `OUT_OF_SCOPE` file **one** issue, its body listing every site.
- Apply is idempotent per finding: a finding whose reply from this round is already
  posted (a partial earlier run) is not replied to again.
- The **state block** is written (see below) into the babysit report comment — created
  on the first apply, rewritten on every later one — and the comment's visible part is
  the in-progress report: `## Babysit report — PR #N`, `**Status:** in progress — round
  R of run K`, the Rounds table so far.

**Decision**, evaluated after the actions, first rule that holds, in this order:

| `decision` | `stop_kind` | `stop_reason` | Rule |
|------------|-------------|---------------|------|
| stop | escalate | `systemic-on-pinned-surface` | any disposition `systemic` with `on_pinned_surface` |
| stop | escalate | `discuss` | any `DISCUSS` |
| stop | escalate | `stopped: <REASON>` | `--stop REASON` given (the model's own reason, e.g. `ci`) |
| stop | converged | `second-order` | the round's `signals.second_order` |
| stop | converged | `no-new-findings` | `signals.no_new_findings` |
| stop | converged | `repeats-only` | every disposition carries `repeat_of` |
| stop | converged | `no-in-scope-implement` | no `IMPLEMENT` disposition |
| stop | escalate | `budget` | rounds used in this run ≥ `max_rounds` (default 3; `--max-rounds` sets this run's) |
| continue | — | — | otherwise |

Output (JSON): `{round, run, posted: {replies, resolved, issues: [#…]}, decision,
stop_kind, stop_reason, kselfreview_range, next}`. With `--next` and `decision:
continue`, the tool requests the next review, waits `--wait` (default 300), and `next`
is the following round's packet; otherwise `next` is `null`.

- `--dry-run`: validate, decide, post nothing, write nothing; output as above with
  `posted` all zero and `next` `null`. Works on merged and closed PRs with
  `--since`/`--until` (replay). Without `--dry-run`, a merged or closed PR is refused
  (exit 3).
- A PR whose state block says `stopped` is refused (exit 5, stderr says re-entry needs
  `--reenter`) unless `--reenter`, which starts run `K+1`: budget reset, ledger kept,
  status back to `running`.
- Exit codes: 0 applied (either decision); 2 invalid dispositions; 3 merged/closed
  without `--dry-run`; 5 stopped without `--reenter`; 1 API error — stderr states which
  actions were posted before the failure, and a re-run continues idempotently.

### State block

The last thing in the babysit report comment's body:

```
<!-- kreview-state
{ "version": 1, "pr": <n>, "status": "running" | "stopped", "run": <k>,
  "max_rounds": <n>, "rounds": [ { "n": <round>, "run": <k>, "window": {"since","until"},
  "review_ids": [...], "effort": <str|null>, "requested_at": <iso|null>, "no_show": <bool>,
  "signals": { as the packet }, "dispositions": [ { "id", "verdict", "shape",
  "root_cause", "on_pinned_surface", "repeat_of", "commit", "issue", "reply_url",
  "source", "path", "line", "provenance" } ], "decision", "stop_kind", "stop_reason",
  "commits": [ fix commits named this round ] } ],
  "stopped": { "at", "reason", "kind" } | null, "kselfreview": "pending" | "done" | "na" }
-->
```

`status` reads it into `babysit.*`; `paid_rounds_this_run` is the number of rounds of
the current run whose `requested_at` is set.

### `kreview report <pr> --tldr TEXT --changed TEXT… --kselfreview done|na [--post]`

Renders the report below from the state block and the live PR; `--post` rewrites the
babysit comment with it and sets `status: stopped` (with `stopped.at` now and the last
round's `stop_reason`, or `manual` when the last decision was `continue`); without
`--post` it prints only. `--changed` repeats, one line each (may be given zero times:
the section then says *nothing — pre-PR gates held*). Exit 0; 1 on API error; 3 when
the PR has no state block.

```markdown
## Babysit report — PR #N

**TL;DR:** <--tldr verbatim>

**Verdict:** ✅ merge-ready | ⚠️ needs human decision | ❌ blocked

### Rounds
| Round | Reviewers | Effort | Findings | Suppressed | On original diff | On fix commits | Unknown | Unanchored | Systemic | Implemented | Pushed back | Out of scope | Discuss | Commits |
<one row per recorded round, all runs; Unanchored = dispositioned issue comments>

### What changed because of review
- <--changed lines, or "nothing — pre-PR gates held">

### Pushed back (with reasoning available in-thread)
- <finding gist (first line of body, ≤120 chars) — reply URL, or "in report" for suppressed>

### Out of scope → issues
- <gist — #issue — scope_outcome>

### Open for you (DISCUSS)
- <gist — reply URL — root cause when systemic>

### Systemic root causes
- <root cause — on pinned Surface (yours to decide) | closed in <commit> | filed as #issue>, or "none found"

**Why the loop stopped:** <stop_reason of the last round, or "manual">
**Push-backs:** N of M findings · **CI:** green/red · **Merge conflicts:** none/yes
**Reviewer effort level:** <distinct efforts>; when Lite: "raising it is a repository setting: Settings → Copilot → Code review → Review effort level"
**Fix commits since last review:** <kselfreview_range's commits, or none> · **kselfreview on them:** done / n/a
**Paid rounds:** N this run · N total on this PR (all runs) — no cumulative cap by design (#61 item 7)
**Re-entry:** further rounds on this PR go through `/kbabysit <n>` — from any seat, for any reason

<!-- kreview-state … -->
```

Verdict rule: ❌ when CI is failing or `mergeable` is CONFLICTING; else ⚠️ when any
`DISCUSS` is recorded, the last `stop_kind` is `escalate`, or `unreviewed_commits` is
non-empty with `--kselfreview na`; else ✅.

### `kreview --help`

Names `status`, `round`, `apply`, `report`.

### Skills

`skills/kbabysit/SKILL.md` and `skills/kreview/SKILL.md` contain no `gh `, `git `,
`awk`, `jq`, or `curl` invocation; their procedure names `kreview status`, `kreview
round`, `kreview apply`, `kreview report`, and `kselfreview <range>` — and keeps every
guardrail and judgement paragraph. `kbabysit`'s frontmatter is unchanged.
`skills/kobserve/SKILL.md` names `kreview status` where it reads a babysit report.

## Blocking

The write-side tests run against the scratch repository named by
`KREVIEW_ACCEPTANCE_REPO` (A2): each test clones it, opens its own PR with a
`## Review scope`, posts review comments through the API as the authenticated user (a
human reviewer, free), and closes what it opened. They skip when the variable is unset;
the milestone is not delivered on skips — and `::test_write_side_coverage_is_not_optional`
**fails** rather than skipping in that case, so this milestone's `blocking:` command
cannot exit 0 with J5–J9 unexercised. Without that guard "not delivered on skips" is a
sentence that depends on a human reading the skip count. One test buys a Copilot review
and is gated by `KREVIEW_ACCEPTANCE_PAID=1` (A3). Replay tests run `--dry-run` on #49
history at the cutoff of M1's Blocking note; they use no scratch repository and so
never skip.

| Job | Planner-authored test | Observable proof | Measured on main |
|-----|-----------------------|------------------|------------------|
The baseline on main is **not** uniform, and the column below says which of the three
each test has: a test that *invokes* `kreview` fails with uv's `Failed to spawn:
kreview` (exit 2); `::test_write_side_coverage_is_not_optional` fails on its own
assertion when `KREVIEW_ACCEPTANCE_REPO` is unset and passes when it is set, because it
runs no command; and `::test_skills_contain_no_gh_or_git_commands` fails on the current
skills' contents, also without running a command.

| J5 | `test_m2_the_loop.py::test_help_lists_apply_and_report` | `--help` names all four commands | uv: `Failed to spawn: kreview` (exit 2); no scratch repository, so it never skips |
| J5–J9 | `::test_write_side_coverage_is_not_optional` | fails, not skips, when `KREVIEW_ACCEPTANCE_REPO` is unset, so the `blocking:` command is red when the write side was not exercised (A2) | runs no command: fails its own assertion wherever the variable is unset, and passes on main once it is set |
| J5 | `::test_round_wait_returns_when_a_review_arrives` | a review comment posted 8 s after `round --wait 120` starts is in the packet; `no_show` false; returned before the deadline | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J5 | `::test_round_wait_reports_no_show` | `--wait 5` with nothing new: `no_show` true, 0 findings, exit 0, and `elapsed_s` reaches the deadline (≥ 4.5 s) — an implementation that returns at once does not pass | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J5 | `::test_round_request_buys_a_copilot_review` (paid, `KREVIEW_ACCEPTANCE_PAID=1`) | `--request --wait 300`: `requested` is `requested` and a review by the Copilot login is in the packet | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_replies_resolves_files_an_issue_and_records_state` | IMPLEMENT thread: reply starts ``Fixed in `<sha>` —``, resolved; OUT_OF_SCOPE thread: reply names the issue, resolved; the issue's body carries the finding verbatim and the thread URL; the babysit comment exists with `<!-- kreview-state`; `status` shows `running`, 1 round; decision `continue` | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_files_one_issue_per_class` | two OUT_OF_SCOPE findings sharing a `root_cause`: **one** issue, its body naming both sites, both threads resolved | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_records_an_issue_comment_disposition` | an issue comment dispositioned: no reply anywhere, no thread opened, its id and verdict in the state block, `no-new-findings` (an issue comment is not line-anchored) | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_is_idempotent_on_a_rerun` | the same round applied twice: the second run posts 0 replies, resolves 0, files no second issue, and the thread's comment count is unchanged | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_incomplete_dispositions` | a round finding without a disposition: exit 2, no reply on any thread | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_a_commit_not_on_the_pr` | IMPLEMENT with a foreign sha: exit 2, stderr names the offending commit, nothing posted | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_each_validation_class` | one case per remaining pinned violation — a verdict outside the four, a missing required field, a `systemic` with no `root_cause`: exit 2, stderr non-empty, no reply and no babysit comment | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_an_id_that_is_not_in_the_round` | a disposition for an id the packet never carried: exit 2, stderr names the id, the valid finding's thread untouched | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_a_closed_pr` | a non-dry-run `apply` on a closed PR: exit 3, no reply, no babysit comment | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_fails_closed_when_github_is_unreachable` | nonexistent repository: exit 1, nothing on stdout | spawn fails (exit 2); no scratch repository, so it never skips |
| J6, J7 | `::test_apply_dry_run_posts_nothing_on_a_live_thread` | `--dry-run` with an IMPLEMENT **and** an OUT_OF_SCOPE on real open threads: exit 0, `posted` all zero, no reply, both threads still unresolved, no issue filed, no babysit comment | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J7 | `::test_apply_discuss_stops_and_leaves_the_thread_open` | one DISCUSS: reply posted, thread unresolved, `stop` / `escalate` / `discuss` | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J7 | `::test_apply_dry_run_second_order_on_49_history` | window 14:27–14:30 with two IMPLEMENT (`c121936`): `stop` / `converged` / `second-order`; #49's comment count unchanged across the run | spawn fails (exit 2); no scratch repository, so it never skips |
| J7 | `::test_apply_dry_run_precedence_on_49_history` | same window: two PUSH_BACK → `second-order`, which outranks `no-in-scope-implement`; one systemic `on_pinned_surface` DISCUSS → `systemic-on-pinned-surface` beats second-order; an empty window → `no-new-findings` | spawn fails (exit 2); no scratch repository, so it never skips |
| J7 | `::test_apply_stop_reason_from_the_model` | `--stop ci` with two IMPLEMENT in the second-order window: `stop` / `escalate` / `stopped: ci` — the model's reason outranks convergence | spawn fails (exit 2); no scratch repository, so it never skips |
| J7 | `::test_apply_repeats_only_stops_the_loop` | round 2 whose every disposition carries `repeat_of` into round 1's ledger: `stop` / `converged` / `repeats-only`; and after two rounds **one** babysit comment exists, holding both (D13) | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J7 | `::test_apply_budget_stops_after_max_rounds` | `--max-rounds 1` with one IMPLEMENT: `stop` / `escalate` / `budget` | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J5, J7 | `::test_apply_next_chains_into_the_next_packet` | `apply --next --wait 120` with round 1's window pinned by `--until` and a comment landing after it: `next` holds the following packet with the new finding and the round-1 ledger; the state has 1 recorded round (round 2 is open, not yet applied) | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J9 | `::test_report_renders_and_posts_from_state` | after a stop: the comment carries the Verdict, Rounds row, *Why the loop stopped*, paid rounds, and `status: stopped` in the block; TL;DR verbatim | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J8 | `::test_reentry_is_advised_and_gated` | after the report: `status` → `stopped`, `reentry` is `selfreview` after an unreviewed push; `apply` → exit 5; `apply --reenter` → run 2, `running`, and the next packet shows the budget reset (`used_this_run` 1, not 2) with run 1's dispositions still in `ledger` (A9) | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_stops_on_red_ci` | a PR whose branch carries a workflow that exits 1: once the check settles, `ci.status` `failing`, a failing entry in `ci.checks`, `verdict` `stop: ci-failing`, exit 3 — from a clone on the branch, so `checkout-mismatch` cannot mask it | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_stops_on_draft` | a draft PR: `pr.draft` true, `verdict` `stop: draft`, exit 3 | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_stops_on_empty_scope` | a PR whose `## Review scope` heading has nothing under it: `scope` `{empty, ""}`, `verdict` `stop: scope-empty`, exit 3 | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J10 | `::test_skills_contain_no_gh_or_git_commands` | in neither skill does any fenced line or inline code span begin with `gh`, `git`, `awk`, `jq`, or `curl` — the generic form the Surface pins, not a list of spellings; `kbabysit` names all four subcommands and keeps its frontmatter pin; `kobserve` names `kreview status` | fails on main, and without running a command: both skills are full of `gh` |

Plus the standing gates: `make check` exits 0.

## Advisory

- `kreview report` without `--post` as the model's preview before posting.
- A `--reviewer` other than Copilot for human-only repositories.

## Invariants

- As M1. Additionally: the tool never merges, never requests a review from any Claude
  automation, never force-pushes, never edits the PR body (the scope is the author's).
- Every stop rule in the decision table is the one signed in #34/#61; the order is the
  only thing this brief adds.
- The report's sections and their meanings are `kbabysit` 0.4.0 §5's.

## Non-goals

- A tool-driven `run`. Reviewer formats beyond Copilot and humans. Editing the review
  scope. Cumulative caps across runs.

## Working environment

- As M1. Additionally: `KREVIEW_ACCEPTANCE_REPO` names the scratch repository (A2:
  `kpiteira/kreview-scratch`, private, default branch `main`, created 2026-09-13) —
  the authenticated `gh` user must be able to push branches, open and close PRs, and
  create and close issues there; Copilot automatic review is off there, so only the
  one paid test triggers a review. `KREVIEW_ACCEPTANCE_PAID=1` enables it.
- GitHub Actions is enabled in the scratch repository (the default for a new
  repository); the red-CI test pushes a one-job workflow that exits 1 onto its own PR
  branch, and the check settles in about a minute.
- The tests create branches `kreview-acc/<hex>` and issues titled `kreview-acceptance
  …` in the scratch repository and close them; leftovers from an aborted run are
  harmless and may be deleted by hand.

## Context

- `kbabysit` 0.4.0 §§1–5 and `kreview` 0.4.0 §§3–4 are the verbatim specification of
  the request, wait, act, and report mechanics; the decision table above is §4's stop
  rules with an order.
- The PR author can post review comments on their own PR through
  `POST /repos/{owner}/{repo}/pulls/{n}/comments` (`commit_id`, `path`, `line`,
  `side: RIGHT`); a thread is resolved through the GraphQL `resolveReviewThread`
  mutation; a reply through `POST …/pulls/{n}/comments/{id}/replies`.
- Copilot is documented to repeat comments on re-review even when threads are resolved;
  the ledger (`repeat_of`) is the defence.
- On #49 the commit after the 14:27 review is `c121936` (on the PR head) — the replay
  tests use it as the fix commit.

## Decisions

- **D4**, **D5**, **D7**, **D8** in the spec apply here.
- **D12** — Precedence: escalations before convergence, budget last, so a human's
  decision is never masked by a convergence that would have ended the loop anyway.
  *Rejected:* convergence first — a DISCUSS would vanish behind `second-order`.
- **D13** — The babysit comment is one comment, rewritten, from the first apply (A8).
  *Rejected:* one comment per round — the ledger would be scattered.
- **D14** — A round with no `IMPLEMENT` stops even if the model wanted another look:
  there is nothing new to review. *Rejected:* a `--force-next` — that is the runaway
  loop's verb.

---

**If a stated fact is false, a decision conflicts with what's actually in the codebase,
or an acceptance test contradicts a job: stop and describe what you found. Don't comply,
and don't classify the problem yourself.**
