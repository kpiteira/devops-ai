---
feature: review-loop-runtime
milestone: M1
spec: ../SPEC.md
blocking: uv run pytest tests/acceptance/review_loop_runtime/test_m1_read_side.py -q
---

# Brief 1 — Read side: `kreview status` and the round packet

## Jobs

- **J1** — When a babysit run starts or re-enters, the model can run `kreview status
  <pr>` and get every preflight and re-entry fact with a mechanical verdict, so that
  the run stops before spending anything when a rule says stop, and never re-derives
  those facts with `gh`.
- **J2** — When a round is to be triaged, the model can run `kreview round <pr>` and
  get one packet holding every new finding — review threads and Copilot's suppressed
  comments alike — with computed provenance, prior replies, repeat candidates, the
  reviewers' summaries and effort levels, the issue comments, and the mechanical
  signals, so that triage starts from facts a stranger can re-run, and the second-order
  stop sees the findings that only live in review bodies (#61).
- **J3** — When a human or a planner wants to know what a stop *would* have been on a
  past PR, they can replay any window of that PR's history with `--since`/`--until`
  and read the same packet, so that the loop's rules are measured on real data, not
  argued from memory.
- **J4** — When the model follows the `kreview` and `kbabysit` skills, the fetch,
  suppressed-comment parsing, provenance, and preflight steps are one command each,
  so that the skills carry judgement and the tool carries the mechanics.

## Surface

**Console script** `kreview`, declared in `pyproject.toml` `[project.scripts]` next to
`ksecret`. It runs from inside a clone of the repository (any branch, any worktree). It
fetches the PR head and any review commit the clone lacks into that clone's object
store; it never modifies `HEAD`, the index, the working tree, or any local branch.
Every command accepts `--repo OWNER/NAME` (default: the checkout's GitHub repository as
`gh repo view` resolves it) and `--json` (machine form; without it, the text form).
Logins are spelled as the REST API spells them — an app carries its `[bot]` suffix
(`copilot-pull-request-reviewer[bot]`), whichever API a value was fetched from.
Timestamps are ISO-8601 UTC as GitHub reports them; `--since`/`--until` accept
ISO-8601 with `Z` or an offset (a naive value is UTC).

### `kreview status <pr>`

JSON form, every key present:

| Key | Value |
|-----|-------|
| `pr` | `{number, state: open\|closed\|merged, draft, head_sha, head_ref, base_ref, mergeable: MERGEABLE\|CONFLICTING\|UNKNOWN, author}` |
| `checkout` | `{branch, matches_pr}` — `matches_pr` true when the local `HEAD` is `head_sha` or the current branch is `head_ref`; both `null` outside a clone of the repo |
| `scope` | `{status: present\|missing\|empty, text}` — `text` is the `## Review scope` section body verbatim (up to the next `## ` heading), `""` when absent; `empty` when the heading exists with only blank lines under it |
| `ci` | `{status: passing\|failing\|pending\|none, checks: [{name, status: passing\|failing\|pending\|skipped}]}` for `head_sha`; `failing` if any check failed, else `pending` if any is running, else `passing`, `none` with no checks |
| `reviews` | `{copilot_total, copilot_reviewed_head, copilot_requested, effort_levels, effort_parse_failed, last_reviewed_sha, unreviewed_commits}` — `copilot_total` counts submitted (not PENDING) reviews by a login containing `copilot`, which is the PR's paid-round total; `copilot_reviewed_head` is true when one of those reviews carries `commit_id` `head_sha` (what kbabysit step 1 asks before requesting); `copilot_requested` is true when a review request to the Copilot reviewer is pending on the PR — both are booleans, both false when no Copilot review or request exists; `effort_levels` is the sorted distinct set parsed from `**Review effort level:** X` footers; `effort_parse_failed` is true when Copilot reviews exist and none carries the footer; `last_reviewed_sha` is the commit of the latest submitted review (any reviewer), `null` without one; `unreviewed_commits` lists the commits in `last_reviewed_sha..head_sha`, oldest first, and is `[]` when `last_reviewed_sha` is `null` |
| `boundary` | `{sha, status: ok\|none\|none-reachable\|missing}` — the provenance boundary (definition under `round`) |
| `automation` | `{claude_review}` — true when a check run or workflow on `head_sha` is named like `Claude Code Review` / `claude-code-action` |
| `babysit` | `{report_present, comment_id, status: none\|running\|stopped, run, rounds, paid_rounds_this_run}` — from the issue comment whose body starts with `## Babysit report`; `status`/`run`/`rounds`/`paid_rounds_this_run` come from the state block M2 introduces and are `none`/`0`/`0`/`null` when the comment carries none |
| `reentry` | `none` (no report, or a report with nothing newer than it), `paid` (a review, thread, or issue comment is newer than the report), `selfreview` (a report, commits newer than it, and nothing else newer than it) |
| `kselfreview_range` | `"<last_reviewed_sha>..<head_sha>"`, `null` without a reviewed sha |
| `verdict` | `"ready"`, or `"stop: <reason>"` with the first reason that holds in this order: `merged`, `closed`, `draft`, `scope-missing`, `scope-empty`, `checkout-mismatch` |

Exit code 0 when `ready`, 3 when `stop:`, 1 on any API or network error (one line on
stderr naming the failure, nothing on stdout). Text form: one `key: value` line per key
above in the same order, nested objects flattened as `key.sub: value`, `verdict` last.

### `kreview round <pr> [--since ISO] [--until ISO] [--include-resolved]`

The **window** is `(since, until]`. `since` defaults to the PR's creation time (M2:
the last recorded round's `until`); `until` defaults to now. A review is in the window
by `submitted_at`, a thread by its first comment's `createdAt`, an issue comment by
`created_at`. PENDING reviews are never included.

JSON form:

| Key | Value |
|-----|-------|
| `pr` | `{number, head_sha}` |
| `scope` | as in `status` |
| `window` | `{since, until}` as resolved |
| `boundary` | `{sha, status}` — the commit of the **earliest submitted review** (any reviewer) that is an ancestor of `head_sha`; review commits absent from the clone are fetched by SHA first; `none` when the PR has no submitted review, `none-reachable` when reviews exist but none is an ancestor (all pre-rebase), `missing <sha>` when a review commit cannot be fetched |
| `reviews` | `[{id, author, state, submitted_at, commit, effort, summary}]` in the window, oldest first; `effort` is the footer's word or `null`; `summary` is the body with every `<details>…</details>` block removed and trimmed |
| `suppressed_check` | `{declared, parsed}` — `declared` is the sum of `N` over every `Suppressed comments (N)` heading in the window's review bodies; `parsed` is the number of entries the parser produced |
| `findings` | one entry per line-anchored finding, oldest first — see below |
| `comments` | `[{id: "c<id>", author, created_at, body}]` — issue comments in the window, excluding the comment that carries the babysit report |
| `signals` | `{findings, line_anchored, suppressed, on_original, on_review_fix, unknown, second_order, no_new_findings, approved, ci, effort, copilot_total}` |

A **finding** is `{id, source, reviewer, path, line, anchor_commit, body, url,
provenance, provenance_detail, blame_sha, thread, repeat_candidates}`:

- `source: thread` — one per review thread whose first comment is in the window.
  `id` is `t<databaseId>` of that first comment; `path`, `line` (=`originalLine`),
  `anchor_commit` (=`originalCommit`), `body` (first comment, verbatim), `url` (that
  comment's URL); `thread` is `{id, resolved, outdated, replies: [{author, created_at,
  body}]}` with every later comment of the thread as a reply. Resolved threads are
  excluded unless `--include-resolved`; outdated threads are included and flagged.
- `source: suppressed` — one per entry of a `Suppressed comments` section in a review
  body in the window: a section starts at a heading whose text begins `Suppressed
  comments` and ends at a line beginning `- **Files reviewed` or at the body's end; an
  entry starts at a line that is exactly `**<path>:<line>**` outside a code fence and
  runs to the next entry or the section end; `body` is the entry's text after that
  header line, verbatim (its code snippet included). `id` is `s<review-id>-<n>`, `n`
  1-based within the review; `anchor_commit` is the review's commit; `url` is the
  review's `html_url`; `thread` is `null`.
- `provenance` is `original` when `blame_sha` (the commit `git blame` names for `line`
  of `path` at `anchor_commit`) is an ancestor of the boundary; `review-fix` when the
  boundary is a proper ancestor of `blame_sha`; otherwise `unknown`, with
  `provenance_detail` naming why (`no submitted review`, `no reachable submitted
  review: N reviews, all pre-rebase`, `review commit <sha> not fetchable`, `blame
  failed`, `not in this PR's history`).
- `repeat_candidates` — ids of findings on this PR earlier than the window on the
  same `path` within 5 lines of `line`.

A **review-level remark** — prose in a review body carrying no `path:line` — is not a
finding and gets no id: it reaches the model as that review's `summary`, which the model
reads as the reviewer's framing of findings that already have ids. Only issue comments
(`c<id>`) are dispositionable without a line, which is what `Unanchored` counts in the
M2 report. A round whose reviews carry only such prose therefore has `line_anchored: 0`
and `no_new_findings: true`, which is the reading kbabysit 0.4.0 §4 already signs.

`signals`: `findings` = `line_anchored` = number of entries in `findings`;
`suppressed` = those with `source: suppressed`; `on_original` + `on_review_fix` +
`unknown` = `line_anchored`; `second_order` = `line_anchored ≥ 1 and on_review_fix ==
line_anchored`; `no_new_findings` = `line_anchored == 0`; `approved` = any review in
the window with state `APPROVED`; `ci` as in `status`; `effort` = distinct efforts of
the window's reviews; `copilot_total` as in `status`.

Exit codes: 0 with the packet; 1 on API or network error (stderr names it, stdout
empty); 4 when `suppressed_check.declared != parsed` (stderr names both numbers; no
packet — a parser mismatch is never an empty round).

Text form, in this order: a header with the PR, head, window, and boundary; the scope
text; each review as `author · effort · state · submitted_at` followed by its summary;
each finding as one line `[<id>] <source> <path>:<line> <provenance>` followed by its
body verbatim and its replies (`author: body`); the comments; the `signals` block as one
`key: value` line per signal, booleans spelled `true`/`false`. Every finding id and
every `path:line` appears verbatim.

### `kreview --help`

Names `status` and `round`.

### Skills

`skills/kreview/SKILL.md` step 1 is `kreview round` (the packet's fields, in prose,
instead of the fetch, suppressed-parser, provenance, and effort blocks — no `git blame`,
no `reviewThreads` query, no `awk`). `skills/kbabysit/SKILL.md` steps 0 and 0b are
`kreview status` and its verdict/`reentry` fields; step 2's effort read is the packet's
`reviews[].effort`. Replies, resolves, issues, the wait, and the report stay as they
are until M2. The judgement text of both skills is unchanged.

### Docs

`README.md` names `kreview` beside `ksecret` where the one-time
`uv tool install -e . --reinstall` is stated.

## Blocking

Every J1/J2/J3 test runs the real console script (`uv run --project <root> kreview …`)
against the real GitHub API from inside the repository clone; nothing is mocked. The two
J4 tests are the exception and check no command at all: they read `README.md` and the two
`SKILL.md` files from disk, because what J4 delivers is text in those files. Fixtures are
merged PRs of this repository. A merged PR's **commits** are immutable, but its reviews
and issue comments are not — anyone can still comment on #49 — so every assertion on a
count, a set of findings, or a comment list passes an explicit `--until` at the
post-merge cutoff (`2026-09-13T17:00:00Z`; #49 merged 16:12:15Z, last activity
16:12:13Z). Without the cutoff a later comment turns the suite red with the
implementation unchanged, which is the corrupted signal the `test-quality` rule forbids.
`status` has no window, so its two live counts (`copilot_total`, `effort_levels`) would
only move if someone submitted a *review* on a merged PR; that is recorded here as the
residual, not papered over with a `>=`.

| Job | Planner-authored test | Observable proof | Measured on main |
|-----|-----------------------|------------------|------------------|
| J1 | `test_m1_read_side.py::test_help_lists_status_and_round` | `--help` exits 0 naming both commands | `uv run kreview --help` → uv: `Failed to spawn: kreview` (script not declared) |
| J1 | `::test_status_on_merged_pr_49` | exit 3, **every key of the table above present** (a status missing `checkout` or `automation` is not this command), `verdict` `stop: merged` while `checkout.matches_pr` is false — so `merged` outranking `checkout-mismatch` is graded too; scope present naming J7, 13 Copilot reviews all `Lite`, boundary `5a9b106`, report present | same — every M1 test fails on main because the script does not exist; the table records the first assertion each would fail on once it runs |
| J1 | `::test_status_without_repo_resolves_it_from_the_checkout` | the same call with no `--repo`, run from the clone: same PR and verdict — every other test passes `--repo`, so the documented default would otherwise ship ungraded | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J1 | `::test_status_reports_missing_scope_on_10` | `scope.status == missing`, `text == ""`, exit 3 | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J1 | `::test_status_reentry_advice_on_49` | `reentry == paid` (reviews after the report), `last_reviewed_sha` `7b2b313`, `kselfreview_range` ends at the head | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2 | `::test_round_full_history_49_parses_every_suppressed_finding` | at the cutoff: `suppressed_check` 15/15; default excludes the 4 resolved threads, `--include-resolved` includes them; `s5191010581-1` (`:245`) blames to `23ee88a2` and `-2` (`:160`) to `63465ed7`, both `review-fix` | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2, J3 | `::test_round_window_second_order_on_49` | the 14:27:15Z review alone: 2 suppressed findings, both review-fix, `second_order` true, `effort` Lite, `summary` free of the suppressed section and the footer | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2, J3 | `::test_round_window_approval_only_on_49` | the 14:34:49Z review alone: 0 findings, `no_new_findings` true, `approved` false (Copilot approves in a COMMENTED review), summary says *Approval recommended* | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2, J3 | `::test_round_first_review_on_27_is_all_original` | window to 15:09Z: boundary `84197e4`, 11 findings (8 suppressed + 3 threads), all `original` | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2, J3 | `::test_round_sixth_review_on_27_is_not_second_order` | window of the 16:13:32Z review: 5 findings (4 suppressed + 1 thread), 4 review-fix, 1 original (`skills/kworktree/SKILL.md:136` → `ed2338dd`), `second_order` false — the thread-only reading called this round second-order | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2 | `::test_round_thread_finding_carries_anchor_and_replies` | `t3998793921`: `azurekeyvault.py`, line 162, anchor `23ee88a`, resolved, outdated, a reply by the author | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2 | `::test_round_repeat_candidates_by_path_and_line` | `s5191010581-2` (line 160) lists `t3998793921` (line 162, earlier) as a repeat candidate | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2 | `::test_round_comments_exclude_the_babysit_report` | at the cutoff: 12 comments on #49 (13 minus the babysit report), ids `c<id>`, none starting `## Babysit report` | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2 | `::test_round_text_form_carries_ids_bodies_and_signals` | the text form of the 14:27 window contains `s5191010581-1`, `azurekeyvault.py:245`, the finding's first sentence, and `second_order: true` | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2 | `::test_round_fails_closed_on_api_error` | a nonexistent repository: exit 1, empty stdout, stderr names it | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J2 | `::test_round_leaves_the_clone_untouched` | `HEAD`, branch list, and `git status --porcelain` identical before and after `round 49` | spawn fails: `Failed to spawn: kreview` (exit 2) |
| J4 | `::test_readme_names_the_new_script` | the README paragraph stating the one-time reinstall names `kreview` beside `ksecret` | fails on main: that paragraph names only `ksecret` |
| J4 | `::test_skills_delegate_fetch_and_preflight_to_the_tool` | `kreview` skill names `kreview round` and has no `git blame`, `reviewThreads(`, or `awk`; `kbabysit` skill names `kreview status` | fails on main: neither skill names the command |

Plus the standing gates: `make check` exits 0.

**Graded here, and not graded here.** Of the verdict order, `merged`, `scope-missing`
and `checkout-mismatch`'s precedence behind `merged` are graded above. `closed`, `draft`
and `scope-empty` are **not**: each needs a PR in that state, and this repository's
merged history has none — M1's fixtures are immutable public PRs by design, and a
mutable fixture is the scratch repository M2 introduces (A5 cuts the milestones that
way). Recorded rather than quietly absent, so the sign-off sees the residual: the three
are gradable in M2's scratch repository if the human wants them blocking there.

## Advisory

- A `--cache` of fetched reviews per PR head for repeated replays — not required.
- The text form fitting one screen for a typical round is the point of the packet; a
  round of 20 findings will not, and that is fine.

## Invariants

- The tool never modifies `HEAD`, the index, the working tree, or a local branch.
- No token in argv or environment of any process the tool spawns: `gh` authenticates
  itself (D1). Nothing the tool prints is a secret.
- No new entry in `[project.dependencies]`.
- The judgement sections of both skills are moved intact; `kbabysit` keeps its
  frontmatter pin (`tests/architecture/test_v2_contract.py`).
- `ksecret` and `kinfra` are untouched.

## Non-goals

- Requesting or waiting for a review, replying, resolving, filing issues, the state
  block, the report — M2. `round` in M1 is a snapshot of what exists.
- Any reviewer body format other than Copilot's and a human's plain comment.

## Working environment

- Standing PR gates: `make check` (ruff, mypy, unit tests, architecture tests) in the
  `check` job; the contract-integrity guard (briefs and `tests/acceptance/**` writable
  only on `spec/*`/`replan/*` — an `impl/*` PR must not touch them); the
  public-surface report (advisory); CodeQL (reporting only). Copilot reviews every PR
  automatically at creation, at the repository's effort setting; later rounds need an
  explicit re-request.
- Toolchain: `uv sync --all-groups --all-extras` (`make setup`). The acceptance tests
  call `uv run --project <root> kreview`, which needs no tool install; `uv tool install
  -e . --reinstall` puts the script on PATH for humans and skills.
- `gh` is authenticated for `kpiteira/devops-ai` (`gh auth status` exits 0) in Karl's
  shell and in executor sessions; the tests need network to `api.github.com` and fetch
  `refs/pull/49/head` and `refs/pull/27/head` into the clone they run in — an executor
  worktree shares the main clone's object store, so the fetch lands there.
- No sandbox: the project's `.devops-ai/project.md` configures none.
- Clock: GitHub timestamps are UTC; the tests pass explicit UTC windows.

## Context

- `skills/kreview/SKILL.md` 0.4.0 §1 carries today's fetch, suppressed parser (awk),
  boundary and provenance shell, all measured against #49 and #27 on 2026-09-13;
  `skills/kbabysit/SKILL.md` 0.4.0 §0/§0b carry the preflight and re-entry checks.
  Those blocks are the specification of this milestone's mechanics, verbatim; the spec's
  Discovered context has the measured numbers.
- `src/devops_ai/cli/ksecret.py` is the console-script precedent (typer app,
  `_emit` writing UTF-8 bytes to stdout regardless of locale — the reason is #58).
- Copilot's login is `copilot-pull-request-reviewer[bot]`; its review commit is the
  `commit_id` on the review; a thread's first comment has `originalCommit` and
  `originalLine`.
- `gh api --paginate` runs a `--jq` filter per page; `gh api graphql --paginate`
  follows `pageInfo` when the query declares `$endCursor`.
- The old scope-less PRs (#10, #20, #23) pre-date the review-scope rule (#34).

## Decisions

- **D1**–**D3**, **D6**, **D7** in the spec apply here.
- **D9** — Resolved threads are excluded by default and `--include-resolved` exists for
  replay: a live round must not re-triage what a prior round resolved, and history has
  everything resolved. *Rejected:* always including them with a flag on each — the
  packet would carry every past finding every round.
- **D10** — `summary` strips every `<details>` block rather than a named subset: the
  overview and file summaries are the reviewer's mechanics, and a round's tokens go to
  findings. *Rejected:* full bodies — the suppressed entries and footer would appear
  twice.
- **D11** — Repeat candidates are computed by path and ±5 lines only; confirming a
  repeat is the model's tag (M2 `repeat_of`). *Rejected:* text similarity — a judgement
  dressed as a metric.

---

**If a stated fact is false, a decision conflicts with what's actually in the codebase,
or an acceptance test contradicts a job: stop and describe what you found. Don't comply,
and don't classify the problem yourself.**
