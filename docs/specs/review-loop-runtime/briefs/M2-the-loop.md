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
  one per site; the issue carries the `issue_title` of the **first finding of the class
  in round order**, so a class whose members disagree about the title still has one
  observable name), and records the round in the PR, so that the model's only writes are
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

### `kreview apply <pr> --dispositions FILE [--next [--wait SECONDS] [--reviewer LOGIN]] [--max-rounds N] [--stop REASON] [--reenter] [--dry-run] [--since ISO] [--until ISO]`

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
on the PR head (fetched first), a `repeat_of` that names no entry of the inherited
`ledger` (an unchecked one would let any string satisfy the `repeats-only` stop), a
missing required field, a `verdict` outside the four.
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
  posted (a partial earlier run) is not replied to again, and a class whose
  `OUT_OF_SCOPE` issue this round already filed is not filed a second time — the two
  together are what "a re-run continues idempotently" (exit code 1, below) means.
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
| stop | escalate | `systemic-repeat` | any disposition `systemic` whose `root_cause` equals the `root_cause` of a `systemic` disposition recorded in the previous round of this run — per-site patches across rounds are never the answer (#49 rounds 6–11) |
| stop | converged | `second-order` | the round's `signals.second_order` |
| stop | converged | `no-new-findings` | `signals.no_new_findings` |
| stop | converged | `repeats-only` | every disposition carries `repeat_of` |
| stop | converged | `no-in-scope-implement` | no `IMPLEMENT` disposition |
| stop | escalate | `budget` | rounds used in this run ≥ `max_rounds` (default 3; `--max-rounds` sets this run's) |
| continue | — | — | otherwise |

Output (JSON): `{round, run, posted: {replies, resolved, issues: [#…]}, decision,
stop_kind, stop_reason, kselfreview_range, next}`. With `--next` and `decision:
continue`, the tool requests the next review, waits `--wait` (default 300), and `next`
is the following round's packet; otherwise `next` is `null`. `--reviewer` is passed to
that round unchanged (default `copilot`; `none` requests nobody and only waits), so a
chained round is addressed to the same reviewer the model names; without `--next` it is
ignored.

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

**Verdict:** ✅ merge-ready (converged: <stop_reason>) | ⚠️ needs human decision (stopped: <stop_reason>) | ❌ blocked (<reason>)

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
non-empty with `--kselfreview na`; else ✅ — so ✅ follows a `converged` stop and nothing
else, and the Verdict line names the signal: `✅ merge-ready (converged: <stop_reason>)`,
`⚠️ needs human decision (stopped: <stop_reason>)`, `❌ blocked (<ci|conflicts>)`. Measured
2026-09-14: three skill-driven reports wrote ✅ over a systemic-repeat stop because the
skill's verdict line was a menu without a rule.

### `kreview --help`

Names `status`, `round`, `apply`, `report`.

### Skills

`skills/kbabysit/SKILL.md` and `skills/kreview/SKILL.md` contain no `gh `, `git `,
`awk`, `jq`, or `curl` invocation in any code — fenced or inline, in any command
position; their procedure names `kreview status`, `kreview round`, `kreview apply`,
`kreview report`, and `kselfreview <range>` — and keeps every guardrail and judgement
paragraph. `kbabysit`'s frontmatter carries no `context: fork` and no `model:` (the
fork was dropped 2026-09-14: it hid the loop; the tier is the babysit session's, and
preflight states the model and stops on the wrong one). `skills/kobserve/SKILL.md` names
`kreview status` where it reads a babysit report.

Dropping that frontmatter turns an existing gate red, so M2 moves the gate with the
mechanism: `tests/architecture/test_v2_contract.py::test_babysit_loop_is_pinned_to_a_forked_opus_subagent`
asserts `context == "fork"`, `agent`, `model` containing `opus` and `background ==
"false"` today, and it runs in `make check` — the always-run gate, not this acceptance
suite. M2 retargets it onto the replacement mechanism (the preflight `MODEL:` check and
the absence of a `context:`/`model:` pin) under a name that matches what it now grades.
Deleting it is not the move: it is the only always-run gate that the loop runs on an
Opus-grade model at all, and issue #25 is the record of what happens when that rule
lives in prose.

A **labeled shell fence** (` ```bash `, `sh`, `shell`, `zsh`, `console`) in those two
skills invokes only: `kreview`, `kselfreview`, `make`, `uv`, and the shell's own
plumbing — `cd`, `cat`, `echo`, `printf`, `sleep`, `mktemp`, `exit`, `set`, `true`,
`false`. Comments and heredoc bodies are not invocations; a `\` continuation is part of
the line it continues, not data. The list is closed on purpose: the two skills are
judgement and guardrails, and a step that needs another command is either the tool's job
(a `kreview` gap — the escape valve) or not a step. Labelled non-shell fences (the
` ```markdown ` report template) and inline spans are held to the blocklist's
**command-position** read only, and to no allowlist at all: measured 2026-09-19,
`gh api x` there is still a finding but `env -i gh api x` is held by neither list
(`::test_j10_prose_code_keeps_the_command_position_read`). Labelling a fence is what
buys it the position-free read, so (decided 2026-09-20) **an unlabeled fence names no
command** — usage lines such as `/kbabysit <pr>` read as none and keep their bare fence;
a bare fence holding `kreview status 66` fails by name until it is labeled — and **no
labeled shell fence opens a heredoc**: a heredoc body is data to every grader, and the
two skills have nothing to write one for, since posting and filing are the tool's job.
A here-string (`<<<"$BODY"`) is not a heredoc and stays allowed.

The model's own commits and pushes (D5: the tool never pushes) are **prose** in the
skills — "commit the fix, push, then apply" — never a fenced `git` line; `apply`'s
refusal of a commit that is not on the PR head is what makes an unpushed fix visible.

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

The baseline on main is **not** uniform, and the column below says which of the three
each test has: a test that *invokes* `kreview` fails with uv's `Failed to spawn:
kreview` (exit 2); `::test_write_side_coverage_is_not_optional` fails on its own
assertion when `KREVIEW_ACCEPTANCE_REPO` is unset and passes when it is set, because it
runs no command; and `::test_skills_contain_no_gh_or_git_commands` fails on the current
skills' contents, also without running a command.

| Job | Planner-authored test | Observable proof | Measured on main |
|-----|-----------------------|------------------|------------------|
| J5 | `test_m2_the_loop.py::test_help_lists_apply_and_report` | `--help` names all four commands | uv: `Failed to spawn: kreview` (exit 2); no scratch repository, so it never skips |
| J5–J9 | `::test_write_side_coverage_is_not_optional` | fails, not skips, when `KREVIEW_ACCEPTANCE_REPO` is unset, so the `blocking:` command is red when the write side was not exercised (A2) | runs no command: fails its own assertion wherever the variable is unset, and passes on main once it is set |
| J5 | `::test_round_wait_returns_when_a_review_arrives` | a review comment posted 30 s after `round --wait 120` starts is in the packet; `no_show` false; returned before the deadline **and after waiting at least 10 s** — the delay is longer than any plausible process start, so the comment cannot pre-date the wait and an implementation that ignores `--wait` cannot read it | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J5 | `::test_round_wait_reports_no_show` | `--wait 5` with nothing new: `no_show` true, 0 findings, exit 0, and `elapsed_s` reaches the deadline (≥ 4.5 s) — an implementation that returns at once does not pass | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J5 | `::test_round_request_reports_already_reviewed` | a submitted review by `--reviewer` exists for `head_sha` (the author's own review comment makes one, free): `requested` is `already-reviewed` and no review request is created — the Surface's "unless a submitted review by that reviewer exists" graded without buying one | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J5 | `::test_round_request_buys_a_copilot_review` (paid, `KREVIEW_ACCEPTANCE_PAID=1`) | one purchase grades all four `requested` outcomes in order: `--request` with no wait → `requested`; the same call again while the request is outstanding → `pending`; `--wait 300` → the Copilot review is in the packet; `--request` once more → `already-reviewed` | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_replies_resolves_files_an_issue_and_records_state` | IMPLEMENT thread: reply starts ``Fixed in `<sha>` —``, resolved; OUT_OF_SCOPE thread: reply names the issue, resolved; the issue's body carries the finding verbatim and the thread URL; the babysit comment exists with `<!-- kreview-state`; `status` shows `running`, 1 round; decision `continue` | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_files_one_issue_per_class` | two OUT_OF_SCOPE findings sharing a `root_cause` but carrying **different** `issue_title`s: **one** issue, titled with the **first finding of the class in round order** (asserted exactly — `in {both titles}` left the selection rule observable nowhere), its body naming both sites, both threads resolved — distinct titles are the point, since grouping by title would pass a test where both titles matched | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_records_a_suppressed_finding_without_replying` | a review whose body carries a `Suppressed comments (1)` section (posted by the author, free): the finding is in the packet with `source: suppressed`, and after `apply` no thread exists anywhere on the PR, no reply was posted, and the state block holds its id and verdict — the Surface's "suppressed findings get no reply, their disposition is recorded" graded live rather than only in dry-run replay | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_stores_reviewer_text_literally` | a finding whose body carries `$(…)`, backticks, `;` and `&&`: the filed issue's body contains that text byte for byte and the shell never ran it (the marker file the payload would create does not exist) — the "reviewer text never passes through a shell" invariant, otherwise ungraded | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_records_an_issue_comment_disposition` | an issue comment dispositioned: no reply anywhere, no thread opened, its id and verdict in the state block, `no-new-findings` (an issue comment is not line-anchored) | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_is_idempotent_on_a_rerun` | the same round applied twice: the second run posts 0 replies, resolves 0, files no second issue, and the thread's comment count is unchanged | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_incomplete_dispositions` | a round finding without a disposition: exit 2, no reply on any thread | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_a_commit_not_on_the_pr` | IMPLEMENT with a foreign sha: exit 2, stderr names the offending commit, nothing posted | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_each_validation_class` | one case per remaining pinned violation, each violating exactly one rule — a verdict outside the four, a `systemic` with no `root_cause`, and every required-field family of the table above: no `shape`; `IMPLEMENT` without `commit`; `IMPLEMENT` without `reply`; `PUSH_BACK` without `reply`; `OUT_OF_SCOPE` without `scope_outcome`; `OUT_OF_SCOPE` without `issue_title`: exit 2, stderr non-empty, no reply, no issue filed, no babysit comment | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_an_id_that_is_not_in_the_round` | a disposition for an id the packet never carried: exit 2, stderr names the id, the valid finding's thread untouched | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_refuses_a_closed_pr` | a non-dry-run `apply` on a closed PR: exit 3, no reply, no babysit comment | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6 | `::test_apply_fails_closed_when_github_is_unreachable` | nonexistent repository: exit 1, nothing on stdout | spawn fails (exit 2); no scratch repository, so it never skips |
| J6, J7 | `::test_apply_dry_run_posts_nothing_on_a_live_thread` | `--dry-run` with an IMPLEMENT **and** an OUT_OF_SCOPE on real open threads: exit 0, `posted` all zero, no reply, both threads still unresolved, no issue filed, no babysit comment | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J7 | `::test_apply_discuss_stops_and_leaves_the_thread_open` | one DISCUSS: reply posted, thread unresolved, `stop` / `escalate` / `discuss` | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J7 | `::test_apply_dry_run_second_order_on_49_history` | window 14:27–14:30 with two IMPLEMENT (`c121936`): `stop` / `converged` / `second-order`; #49's comment count unchanged across the run | spawn fails (exit 2); no scratch repository, so it never skips |
| J7 | `::test_apply_dry_run_precedence_on_49_history` | same window: two PUSH_BACK → `second-order`, which outranks `no-in-scope-implement`; one systemic `on_pinned_surface` DISCUSS → `systemic-on-pinned-surface` beats second-order; an empty window → `no-new-findings` | spawn fails (exit 2); no scratch repository, so it never skips |
| J7 | `::test_apply_stop_reason_from_the_model` | `--stop ci` with two IMPLEMENT in the second-order window: `stop` / `escalate` / `stopped: ci` — the model's reason outranks convergence | spawn fails (exit 2); no scratch repository, so it never skips |
| J7 | `::test_apply_repeats_only_stops_the_loop` | round 2 whose every disposition carries `repeat_of` into round 1's ledger: `stop` / `converged` / `repeats-only`; and after two rounds **one** babysit comment exists, holding both (D13) | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J6, J7 | `::test_apply_refuses_a_repeat_of_outside_the_ledger` | the same round 2 with `repeat_of` naming an id no ledger entry carries: exit 2, stderr names the id, nothing posted and no round recorded — without this an arbitrary string converges the loop through `repeats-only` | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J7 | `::test_apply_systemic_repeat_stops_the_loop` | round 2 carrying a `systemic` disposition whose `root_cause` equals round 1's: `stop` / `escalate` / `systemic-repeat`; and `report` on it renders `⚠️ needs human decision (stopped: systemic-repeat)` — the stop that three skill-driven reports called ✅ | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J7 | `::test_apply_budget_stops_after_max_rounds` | `--max-rounds 1` with one IMPLEMENT: `stop` / `escalate` / `budget` | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J5, J7 | `::test_apply_next_chains_into_the_next_packet` | `apply --next --wait 120` with round 1's window pinned by `--until` and a comment landing after it: `next` holds the following packet with the new finding and the round-1 ledger; the state has 1 recorded round (round 2 is open, not yet applied) | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J9 | `::test_report_renders_and_posts_from_state` | after a stop: the comment carries the Verdict, Rounds row, *Why the loop stopped*, paid rounds, and `status: stopped` in the block; TL;DR verbatim | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J9 | `::test_report_renders_every_changed_line_in_order` | `--changed` given **twice**: both lines appear in *What changed because of review*, in the order given, and the `nothing — pre-PR gates held` fallback does not — the only other report test omits the option, so an implementation that ignored `--changed` entirely passed the suite while J9 makes those lines the model's whole contribution to the section | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J8 | `::test_reentry_is_advised_and_gated` | after the report: `status` → `stopped`, `reentry` is `selfreview` after an unreviewed push; `apply` → exit 5; `apply --reenter` → run 2, `running`, and the next packet shows the budget reset (`used_this_run` 1, not 2) with run 1's dispositions still in `ledger` (A9) | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_is_ready_on_a_fresh_pr` | a freshly opened PR: `verdict` `ready`, **exit 0**, `checkout.matches_pr` true, `boundary.status` `none`, `ci` `{none, []}`, `reentry` `none`, `last_reviewed_sha` null, `kselfreview_range` null — every other `status` test asserts a stop, so the verdict the loop actually starts from was ungraded | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_stops_on_checkout_mismatch` | the same PR read from a clone on the base branch: `verdict` `stop: checkout-mismatch`, exit 3, with the PR open, in scope and green — graded on its own rather than only as the rule `merged` outranks | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J2 (M1) | `::test_round_unknown_provenance_after_a_rebase` | a PR whose reviewed commit is force-pushed out of history: `boundary.status` `none-reachable`, the finding on it `unknown` with `provenance_detail` naming the rebase, `signals.unknown == line_anchored`, `second_order` **false** — the third provenance state, and the signed rule that an unknown never ends a loop, neither of which M1's immutable fixtures can produce | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_stops_on_red_ci` | a PR whose branch carries a workflow that exits 1: once the check settles, `ci.status` `failing`, a failing entry in `ci.checks`, `verdict` `stop: ci-failing`, exit 3 — from a clone on the branch, so `checkout-mismatch` cannot mask it | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_stops_on_draft` | a draft PR: `pr.draft` true, `verdict` `stop: draft`, exit 3 | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_stops_on_empty_scope` | a PR whose `## Review scope` heading has nothing under it: `scope` `{empty, ""}`, `verdict` `stop: scope-empty`, exit 3 | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J1 (M1) | `::test_status_stops_on_scope_missing` | an **open** PR with no `## Review scope` heading: `scope` `{missing, ""}`, `verdict` `stop: scope-missing`, exit 3 — M1 grades the field and the precedence `closed` outranks it, never the verdict, because every M1 fixture is merged or closed | spawn fails (exit 2); skips without `KREVIEW_ACCEPTANCE_REPO` |
| J10 | `::test_skills_contain_no_gh_or_git_commands` | two graders over both skills: (1) **blocklist** — in a labeled shell fence, `gh`, `git`, `awk`, `jq` or `curl` as *any token* of a line is an invocation, whatever precedes it (an assignment, a keyword, a pipe, `$( )`, a wrapper, a wrapper's option, a continuation): the read is position-free, so there is no next position (decided 2026-09-19, below); in inline spans and unlabeled or non-shell fences the read is by command position and an invocation is the command word plus at least one argument, so prose naming the `gh` CLI passes; (2) **allowlist, fail-closed** — the first word of every command in a labeled shell fence is one of the Surface's list, read as written: a wrapper (`sudo`, `env`, `timeout`, `xargs`, `command`, `time`, `eval`, `bash -c`) *is* the command word and is unlisted, so it fails by its own name instead of passing until someone reads past it. Both graders read the command word through its spelling: `"gh"`, `\gh`, `/usr/bin/gh`, `./tools/gh` and `tools/gh` all name `gh`, and `$TOOL` — unresolvable by reading — is named by the allowlist rather than skipped. Fences close on a marker at least as long as their opener; heredoc bodies and `#` comments are skipped; `\` continuations are joined into their line. (3) **reach** (decided 2026-09-20) — no unlabeled fence in either skill names a command (`_unlabeled_fence_commands`), and no labeled shell fence opens a heredoc (`_heredoc_openers`); their own cases are `J10_REACH_CASES` (`::test_j10_reach_assertions_read_what_they_claim`). Also: `kbabysit` names all four subcommands, has no `context: fork`, and keeps its preflight `MODEL:` check; `kobserve` names `kreview status` | fails on main, and without running a command: blocklist 15 lines in `kbabysit`, 23 in `kreview`; allowlist 43 and 79 (measured 2026-09-19 at `47c428e` against this branch's skills, which are main's — `git diff origin/main -- skills/` is empty; re-measured 2026-09-20 after the trailing-comment rule, unchanged); the reach assertions pass on main (0 unlabeled-fence commands, 0 heredocs in either skill, measured 2026-09-20) — they are a constraint the rewrite keeps, not a job it delivers |

Plus the standing gates: `make check` exits 0.

**J10's parser is itself graded.** Every other row here is decided by an API; J10's is
decided by a parser this repository wrote, and a parser that misreads a command position
returns green for the wrong reason. `::test_j10_grader_reads_every_command_position`
holds 21 crafted cases: the six path- and quote-spellings of a command word and the one
indirection (`$TOOL`); the six positions earlier rounds widened the blocklist to reach
(plain, assignment, shell keyword, pipe, env prefix, loop body); the three wrappers only
the allowlist can see (`timeout`, `eval`, `bash -c`); and five lines a correct rewrite
contains that must **not** fail — `kreview`, `make`, a quoted argument, `/kbabysit`, a
comment. It is not blocking — it grades the test file, so it
passes on main — and it is what lets the row above be trusted rather than believed. It
replaces the earlier claim that the parser "was falsified on crafted cases", which named
a number no reader could re-derive; the cases are now in the repository. Measured
2026-09-13, before they were written: of the seven ways to spell a command word that is
not a bare identifier, six passed **both** graders silently — `/usr/bin/gh`,
`./tools/gh`, `../bin/gh`, `"gh"`, `\gh` and `$TOOL` — and the seventh, `tools/gh`,
passed the blocklist. A fail-closed allowlist was failing open on the spellings an
allowlist exists to stop.

## Advisory

- `kreview report` without `--post` as the model's preview before posting.
- A `--reviewer` other than Copilot for human-only repositories.

### Decided 2026-09-19 — J10's grader reads tokens, not positions

Round 4 (Balanced) measured a fifth escape class against the grader on `5c4c5cb`.
`_commands()` stripped wrapper words (`env`, `sudo`, `xargs`, …) before reading the
command, then stopped at the first token it could not classify and yielded nothing for
the whole segment, so an option-bearing wrapper hid the forbidden command from the
**blocklist** entirely:

| input | `_commands()` | blocklist |
|---|---|---|
| `gh api x` | `['gh']` | caught |
| `sudo gh api x` | `['gh']` | caught |
| `nohup gh api x` | `['gh']` | caught |
| `env -i gh api x` | `[]` | **escapes** |
| `env -u HOME git push` | `[]` | **escapes** |
| `xargs -0 gh api x` | `[]` | **escapes** |
| `sudo -u bob gh api x` | `[]` | **escapes** |
| `command -v gh api` | `[]` | **escapes** |
| `time -p gh api x` | `[]` | **escapes** |

And a `\` continuation was dropped as data, so a fence containing `kreview status 66 \`
followed by `| jq '.verdict'` yielded no invocation at all: the `jq` was invisible to
both graders. Raised by Copilot as three findings (two threads on the test, one on this
brief's own "continuations are skipped" sentence). Same root cause the 2026-09-13
self-review had closed one round earlier, at its next position; per `kbabysit` §4 and
this spec's own systemic-repeat rule, round 4 escalated instead of patching a fifth time.

**Decision (Karl, 2026-09-19):** the grader stops parsing shell positions. In a labeled
shell fence the blocklist reads every token of a line and fails on a forbidden word
wherever it stands; the allowlist reads the first word of each command as written, so a
wrapper is judged by its own name and is unlisted; continuations are joined into the
line they continue. Every escape in the table above, and the continuation, is a row of
`J10_CASES` (`::test_j10_grader_reads_every_command_position`), with `allowed-*` rows
proving a continued `uv run` line and a path argument (`tests/unit/test_git.py`) do not
fail — the latter only because its basename is `test_git.py`. **The wider read costs
precision, and the cost is pinned rather than claimed away:** a forbidden word is a hit
wherever it stands, so `cat docs/notes/git` (basename) and `printf "%s" "run jq on it"`
(inside a quoted argument) are findings in a shell fence. Both are `J10_CASES` rows.
Prose code (inline spans, unlabeled and non-shell fences) keeps the command-position
read, because `use jq to filter` in a `text` fence is not an invocation.
*Rejected:* patching the parser to scan past unclassifiable tokens — one more position,
and the sixth revision of the same reader; replacing it with a lexer (`shlex`) — a lexer
tokenizes `env -i gh` correctly and leaves the wrapper-stripping mistake intact, since the
escapes lived in what the grader did with the tokens, not in how it split them; deferring
to M2 — leaves the grader unmeasured until an executor is already running under it.
What remains outside the blocklist's read, measured 2026-09-19 rather than reasoned:
a command inside a string (`eval "gh …"`, `bash -c '…'`) — which the allowlist does
catch, by the interpreter's name, and both rows stay in the case table with the two
verdicts differing on purpose — and three the allowlist does **not** catch, because they
are deliberately not code it reads: a heredoc body, a `#` comment, and prose code
(above). Each is a `J10_CASES` or prose-code row, so this list is re-derivable instead of
asserted. Two of those three had no second line of defence; they are decided below.

### Decided 2026-09-20 — the gate's reach: label the fence, write no heredoc

Not a position (that class is closed above) but the read's **reach**, measured
2026-09-19 through the real graders, not reasoned:

| code | blocklist | allowlist |
|---|---|---|
| `env -i gh api x` in a ` ```bash ` fence | catches | catches |
| `env -i gh api x` in an **unlabeled** ` ``` ` fence | misses | does not run |
| `env -i gh api x` in a ` ```text ` fence or an inline span | misses | does not run |
| `gh api x` inside a **heredoc body** in a ` ```bash ` fence | misses | does not run |

The `text`-fence and inline-span rows are the decision above working as intended — that
code is prose. The other two are the fail-open shape the allowlist exists to prevent: an
M2 executor who writes a shell block and forgets the ` ```bash ` label, or who generates
a script through a heredoc, passes a gate that is supposed to fail closed, and nothing
tells them. Neither is exercised today, measured rather than assumed: the only unlabeled fence in
either skill holds `/kbabysit <pr>` usage lines (which read as no command, so widening
the reader would not fail them), and neither skill opens a heredoc. Both skills do use
here-strings (`<<<"$BODY"`), which `_HEREDOC` correctly declines to read as an opener —
true by the width of one `\w+`, and graded from now on by the `here-string` row.

Run 5 did not patch it — a sixth consecutive change to one grader, on a boundary signed
the same day, is an escalation — and put four options to Karl.

**Decision (Karl, 2026-09-20):** two assertions, no change to any reader. (1) **An
unlabeled fence names no command**: `_unlabeled_fence_commands` runs the command-position
read over every bare ` ``` ` fence and fails on any command word, allowed or not — the
message says to label it. Usage lines (`/kbabysit <pr>`) and placeholders read as no
command, so the one bare fence either skill has today stays as it is. (2) **No labeled
shell fence opens a heredoc**: `_heredoc_openers` fails on an opener, so there is no body
for the graders to be blind to. The two skills have nothing to write a heredoc for —
posting a comment and filing an issue are `kreview`'s job — and a here-string is not an
opener. Both pass on main (measured: 0 and 0), so they constrain the rewrite rather than
grade a job; each has its own case table (`J10_REACH_CASES`).
*Rejected:* reading unlabeled fences as shell — closes the same half by widening the
reader, and a reader is what every one of the five escapes lived in; reading heredoc
bodies — gives up "a heredoc body is data" to grade a construct the skills should not
contain; accepting both holes as documentation — the executor who forgets a label is the
plausible case, and being told is cheaper than a review round finding it.

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
  branch; the test polls `status` until the check settles, up to 240 s.
- The tests create branches `kreview-acc/<hex>` and issues titled `kreview-acceptance
  …` in the scratch repository and close them; leftovers from an aborted run are
  harmless and may be deleted by hand. Two of them go further on their own branch, and
  both rest on behaviour measured against the scratch repository on 2026-09-13 rather
  than assumed:
  - A **COMMENT review carrying a body** can be submitted by the PR's own author (only
    *approving* one's own PR is refused), and a plain review comment by that author is
    itself a submitted review whose `commit_id` is the head. The first is how a
    `Suppressed comments` section is produced without buying a Copilot review; the
    second is how `already-reviewed` is graded free.
  - After a **force-push**, the review keeps its original `commit_id`, that commit is
    still served by GitHub (`git fetch origin <sha>` succeeds from a fresh shallow
    clone) and is no longer an ancestor of the head, and the thread survives with its
    `originalCommit` — which is why the expected boundary is `none-reachable` and not
    `missing`.

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
