---
name: kbabysit
description: Drive a PR from ready-for-review to merge-ready — request Copilot review, wait for it, triage and address comments via kreview against the PR's written review scope, re-request, and stop when the reviewer has finished with the PR (not with the fixes). Ends with a TL;DR report. Never merges, never triggers Claude reviews.
metadata:
  version: "0.5.0"
---

# kbabysit — babysit a PR to merge-ready

Orchestrates the review loop for one PR: request reviews → wait → triage/address (via
`kreview`) → decide on re-review → repeat. The loop ends when the reviewer has finished
reviewing **the PR**. A reviewer never stops finding things; after a few rounds it is
reviewing the previous round's fix, and each fix invites the next finding. Two loops ran
13 and 11 paid rounds that way on 2026-09-12, every finding true, most of them outside
what the PR was for. Truth is not the axis; scope is.

```
/kbabysit                # PR for the current branch
/kbabysit <pr-number>
/kbabysit <pr-number> max-rounds: 5   # raise the round budget (default 3, applied in step 4)
```

**Arguments for this run:** `$ARGUMENTS` — empty means "the PR for the current branch".

## How this runs — in its own session, on Opus

This loop runs **in the session that invokes it**, and that session is an Opus-grade
agent-deck session created from the PR's worktree:

```bash
agent-deck add <worktree> -t <project>/babysit-<pr> -g <project> -c claude --model claude-opus-5
agent-deck session start <project>/babysit-<pr>
agent-deck session send <project>/babysit-<pr> '/kbabysit <pr>'   # give the agent ~3s to come up
```

**This is the repo's launch contract, not a recipe of its own** — the same three steps, in
the same order, as `skills/kobserve/SKILL.md`, `skills/kworktree/SKILL.md` and
`src/devops_ai/cli/impl.py` (`add_session` → `start_session` → `send_to_session`). Copy it
from one of those rather than from memory; each element is there because something broke
without it:

- **`-g`** — a session added without a group inherits its parent's, and groups default to a
  running-session cap of 1 that counts the parent, so a babysit launched from another
  agent-deck session queues or errors instead of starting (pilot, 2026-09-06).
- **`session start`** — `add` only registers the session; it does not run the tool. Send to
  a session that was never started and the kickoff goes nowhere, so the babysit never
  begins.
- **the pause before `send`** — `send_to_session` sleeps 3 s after start for the same
  reason ("to allow the agent to start"), and a busy target times out at 60 s and returns
  failure rather than queueing. If the kickoff does not land, re-send it; nothing else in
  the loop retries it for you.

Two reasons for the tier and the visibility, both measured:

- **Tier.** Babysitting is polling plus bounded per-finding judgement, executor-tier work;
  the planner tier belongs to the intent and acceptance decisions this loop feeds. On
  2026-09-03/04 the loop ran inline on a top-tier session because the skill named no tier
  (agent-memory #246, devops-ai #25); the human saw it again on 2026-09-12 and #45 pinned
  the tier in frontmatter with `context: fork` + `model: claude-opus-5`.
- **Visibility.** The fork fixed the tier and hid the loop: a forked run leaves the
  invoking session showing a status line and nothing else, with every round's reasoning in
  a sidechain transcript nobody opens. Measured 2026-09-13 on devops-ai #72 and #66 — two
  full babysits, two empty panes. The human's word on 2026-09-14: drop the fork. The tier
  is now the session's, and step 0 checks it instead of the frontmatter forcing it.

What that costs you, and how this skill pays it:

- **The session sees no planner conversation** — only this file with `$ARGUMENTS`
  substituted and whatever the kickoff said. So the PR number must either be passed
  explicitly (`/kbabysit 42`) or be resolvable from the checkout. Step 0 reads the explicit
  number **first** and only falls back to `gh pr view` — the other order silently babysits
  the branch's PR when you asked for a different one — and stops outright if the two
  disagree, because the loop pushes fixes and `kreview` resolves the PR from the checkout
  too. A session created from the PR's worktree resolves correctly by construction.
- **The report lands in this session's turn** and in the PR comment. The ownership rule
  below — an unread review round is not done — is why the session that runs this loop has
  no other job: nothing moves on before the report is read.
- **`kreview` runs in this same session**, per round, never forked — forking it would hide
  each round's reasoning from the loop that has to decide whether to run another one.
  Invoke it with the Skill tool; if that tool is missing wherever this runs, read and follow
  `~/.claude/skills/kreview/SKILL.md` directly instead — same contract either way.

**End state:** merge-ready (or explicitly blocked) + a detailed report with TL;DR. This skill
never merges and never closes a DISCUSS item on its own — those are the human's calls.

**Ownership.** A session that opens a PR owns its review rounds — every PR, milestone or
not — until the PR is merge-ready or it hands off explicitly. The v2 pilot's one unread
Copilot round sat overnight on a side PR nobody owned. For a milestone PR the executor's
*For the human* section is not this loop's to close: it goes to the human before merge
(`kobserve` verify).

---

## 0. Preflight

**Model first.** Say which model this session runs on — the harness names it — as a
`MODEL:` line. `MODEL: claude-opus-…` continues. Anything else — a Fable/Mythos planner
session, a Sonnet or Haiku session, a session that resumed on a default after a restart —
ends the run here: `MODEL: <id> — not the executor tier; launch an Opus agent-deck session
from this PR's worktree and run /kbabysit <n> there`. The tier used to be forced by
`context: fork` in this file's frontmatter; the fork hid the loop, so the check is yours
now and this line is what keeps it from being skipped.

**Re-run this gate on every resume, not just at step 0.** The frontmatter pin was
re-applied to each fork, so it survived a restart; a one-shot preflight does not, and the
model is a property that changes underneath a running loop. Measured in the pilot
(`docs/designs/v2-contract/PILOT.md`, 2026-09-08): after a tmux restart
`agent-deck session start` resumed a planner on Opus 4.8 instead of Fable — the session's
model setting did not survive — and the rest of that session ran on the weaker model
unnoticed until someone read the status bar. If this session was restarted or resumed
mid-loop, state the `MODEL:` line again before the next round and apply the same stop.

```bash
ARG_PR=$(printf '%s' "$ARGUMENTS" | sed 's/^#//' | grep -oE '^[0-9]+')      # explicit <pr-number>, if given
BRANCH_PR=$(gh pr view --json number -q '.number' 2>/dev/null)              # this checkout's own PR, if any
PR_NUMBER="${ARG_PR:-$BRANCH_PR}"

if [ -z "$PR_NUMBER" ]; then echo "TARGET: none — no number in the arguments and no PR open for this branch"
elif [ -n "$ARG_PR" ] && [ "$ARG_PR" != "$BRANCH_PR" ]; then echo "TARGET: not this checkout — #$ARG_PR vs branch PR #${BRANCH_PR:-none}"
else echo "TARGET: #$PR_NUMBER"; fi

REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
gh pr view "$PR_NUMBER" --json state,isDraft,mergeable,headRefName,baseRefName,statusCheckRollup
```

**Anything but `TARGET: #N` ends the run before step 1** — say which of the two it was and
stop. The second case looks harmless and is not: this loop does not only *read* a PR, it
commits and pushes fixes, and `kreview` resolves the PR from the checkout the same way. Given
`/kbabysit 42` from a branch whose PR is #43, a naive run would poll #42's reviews and push
#42's fixes onto #43. Babysitting a PR means being on its branch; the fix is
`git checkout` (or `gh pr checkout 42`), not a cleverer argument.

- PR closed/merged → report and stop.
- Draft → mark ready (`gh pr ready`) only if the work is actually complete; otherwise stop.
- **Review scope present → else stop.** The PR body must carry a `## Review scope` section:
  the outcomes this PR delivers, in the author's words, one line each (a milestone PR lists
  the brief's jobs). Every finding in every round is judged against it, and a stranger
  reading the report can check that judgement.

  ```bash
  BODY=$(gh pr view "$PR_NUMBER" --json body -q '.body')
  if ! grep -q '^## Review scope' <<<"$BODY"; then echo "SCOPE: missing"
  elif [ -z "$(sed -n '/^## Review scope/,/^## /p' <<<"$BODY" | grep -v '^## ' | grep -v '^[[:space:]]*$')" ]; then echo "SCOPE: empty"
  else echo "SCOPE: present"; fi
  ```

  Anything but `SCOPE: present` ends the run before step 1 — a heading with nothing under
  it is not a scope. **Stop and say what is missing** — the section's name, what goes in it,
  and that the loop starts once the author adds it. kbabysit never writes it: a scope
  derived from the diff makes everything in the diff in scope by construction, including
  whatever later rounds add, and the fence is gone before the first round.
- **CI red → fix CI first.** Reviewers reviewing broken code wastes a round. Diagnose, fix,
  push, wait for green, then start the loop.
- Detect the repo's review automation so you don't double-request:
  - **Copilot:** automatic review (repo/org ruleset) typically fires on PR **creation** only;
    updates need an explicit re-request unless the ruleset enables "review new pushes". If a
    Copilot review already exists for the current head, don't request another.
  - **Copilot's review effort level** — record it, you cannot request it. Every Copilot
    review body ends with a `Review effort level:` line. Preflight asks only **what level
    this PR has been reviewed at so far** — the per-round level is read in step 2, off that
    round's own review, because at preflight the round's review does not exist yet and a
    level read here could only ever describe somebody else's round:

    ```bash
    # Identical predicate in both filters — submitted Copilot reviews, nothing else. A
    # PENDING review has no published body, so counting it while not counting its (absent)
    # footer reports a broken parser that isn't one; this is the same `state != "PENDING"`
    # predicate kreview's parser uses, and it has to stay the same one.
    # --paginate runs the --jq filter per page, so `length` yields one count per page: sum
    # them. Reporting from page 1 alone goes wrong at 30+ reviews, exactly where it matters.
    gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/reviews" \
      --jq '[.[] | select(.state != "PENDING" and (.user.login | test("copilot"; "i")))] | length' \
      | awk '{n += $1} END {print "copilot reviews so far: " n+0}'

    gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/reviews" \
      --jq '.[] | select(.state != "PENDING" and (.user.login | test("copilot"; "i"))) | .body // ""' \
      | grep -oE 'Review effort level:\*\* *[A-Za-z]+' | sed -E 's/.*\*\* *//' \
      | sort -u | tr '\n' ' '      # the distinct levels seen, not the last one found
    ```

    No level with **zero** reviews is simply "none yet". No level with reviews **present**
    is a broken parser — GitHub renamed or moved the line — and the report says so rather
    than printing `—`. Take the distinct set, never `tail -1`: the last *matching* line is
    not the newest *review*, so a newest review that dropped the footer would be masked by
    an older one and the broken-parser path would never be reached.

    `Lite` is GitHub's default, and it is what all 25 Copilot reviews across #49 and #51
    reported on 2026-09-13 (13 and 12, measured). **It is a
    repository/organization setting, not a request-time parameter** — verified against
    [Configuring Copilot code
    review](https://docs.github.com/en/copilot/how-tos/copilot-on-github/set-up-copilot/configure-code-review):
    the setting is named **"Review effort level"** (`Lite` | `Balanced`) and lives at
    **repository → Settings → "Code, planning, and automation" → Copilot → Code review**
    (organizations have the same page, as the default their repos inherit). The REST
    review-request endpoint takes `reviewers` and `team_reviewers` and nothing else, and
    the GraphQL `RequestReviews` input has no effort field, so `gh pr edit --add-reviewer
    @copilot` — this skill's only request verb — always runs at the repo default. The web
    UI's per-review dropdown is unreachable from here.

    So: this loop **never changes the setting** and never claims to have raised it. It
    records the level per round in the report, and when the level is `Lite` the report's
    *For the human* line says that a deeper first pass is one toggle on that settings page
    — his call, his money: GitHub's [code review
    concepts](https://docs.github.com/en/copilot/concepts/agents/code-review) page
    estimates "$0.05 USD to $1 USD worth of AI credits with 'Lite' effort, and $0.25 USD
    to $5 USD with 'Balanced'". The hypothesis worth measuring once he flips it is whether
    the first pass finds more and the round count drops — which is why the report carries
    the level per round rather than once.
  - **Claude reviews are out of scope — cost.** They are expensive and have caused runaway
    costs; they're meant to be unplugged from these repos. If you find Claude review
    automation still wired up (an `anthropics/claude-code-action` workflow on `pull_request`
    events, or a "Claude Code Review" check run appearing), don't touch it — but **flag it
    prominently in the final report** so the human can unplug it for real.

## 0b. Re-entry check — before spending anything

**If a babysit report is already posted on this PR, this run is a re-entry and decides here,
not in step 1.** Without this branch the re-entry rule is a promise nothing executes: a run
triggered only by "HEAD moved" would walk into step 1 and buy a Copilot round, which is
exactly what `kselfreview` is supposed to cover.

```bash
gh api --paginate "repos/$REPO/issues/$PR_NUMBER/comments" \
  --jq '.[] | select(.body | test("^## Babysit report")) | "\(.created_at)"' | tail -1
LAST_REVIEWED_SHA=$(gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/reviews" \
  --jq '.[] | select(.state != "PENDING") | .commit_id' | tail -1)
git log --oneline "$LAST_REVIEWED_SHA..HEAD"     # the unreviewed commits, if any
```

- **No prior report** → first run; go to step 1.
- **Report present, and the only change since is fix commits nobody has reviewed** →
  run `kselfreview <last-reviewed-sha>..HEAD` (the range form, never the bare one), act on
  what it finds, append to the existing report. **Do not request a review.** This is the
  case the second-order stop hands forward, and buying a round for it is the spend the rule
  exists to prevent.
- **Report present, and something genuinely new needs a reviewer** — the human asked, a
  relayed finding turned out to be real, the PR changed substantively — → go to step 1, and
  count this round against the budget *and* against the PR's running total (step 4).

Whichever branch runs, every stop rule in step 4 applies to it.

## 1. Request the review

If Copilot hasn't reviewed the current head SHA and won't auto-fire:

```bash
# Same command requests and re-requests
gh pr edit "$PR_NUMBER" --add-reviewer @copilot
```

Human reviewers need no requesting — any comments they've left get triaged in the same round.

## 2. Wait for the review to complete

Poll with `sleep`-and-check: a new review by `copilot-pull-request-reviewer[bot]` in
`repos/$REPO/pulls/$PR_NUMBER/reviews` with `submitted_at` after the request means done.
Usually lands within a minute or two — poll every 30–60s, give up after ~5 min.

**Record this round's effort level here**, from the review you just waited for — you have
its id, so read that review and nothing else:

```bash
gh api "repos/$REPO/pulls/$PR_NUMBER/reviews/$REVIEW_ID" --jq '.body // ""' \
  | grep -oE 'Review effort level:\*\* *[A-Za-z]+' | sed -E 's/.*\*\* *//'
```

Empty here is unambiguous — this review exists and carried no footer — so it is a broken
parser, not a missing round, and the report's `Effort` column says `?` rather than `—`.
Reading the level off the round's own review is the whole point: a grep across the PR's
review history answers a different question and cannot attribute a level to a round.

While waiting, also watch CI for the same head SHA — a red check that local gates missed is
round feedback exactly like a review comment, and it gets fixed in the same round.

On timeout, proceed with whatever arrived and record the no-show in the report — don't stall
the loop on a reviewer that never comes.

## 3. Triage and address — one kreview round

Run `kreview` in **autonomous mode** for this round. It resolves the PR from the checkout,
which step 0 has already established is `$PR_NUMBER` — that check is what makes this safe.
It fetches the full review surface
(review bodies **including their `Suppressed comments` sections**, threads with
resolved/outdated state, issue comments, CI), gives each new
finding its **provenance** (on the PR's original diff, or on a review-fix commit), asks
**isolated or systemic** of each before deciding anything, hands out one of
four dispositions — IMPLEMENT / PUSH BACK / DISCUSS / OUT OF SCOPE — implements what's real
and in scope with gates green, files an issue for each out-of-scope finding, replies to every
thread, resolves handled ones, pushes, and returns a round report.

Two of its columns are this loop's inputs, not the round's own business:

- **Suppressed findings are line-anchored findings.** They carry a `path:line`, get a
  computed provenance, and count in the provenance totals — so the second-order stop below
  sees them. On #49 only 4 of the 13 Copilot reviews opened a thread at all; from round 6
  on, 7 of the last 8 opened none, so a loop reading threads alone saw seven empty rounds
  and paid for each. Counting the suppressed ones fires the second-order stop at round 6.
- **`systemic → <root cause>`** on pinned Surface is an escalation, below.

The babysitter's own rules on top:

- **Never weaken a test, gate, or threshold to satisfy a reviewer** — that's a DISCUSS with
  the human, not an implement.
- A reviewer comment that fights the architecture is an ACP-shaped question — escalate,
  don't loop on it.
- Keep the round's push to one coherent commit (or a few logical ones); in auto-review repos
  every push spends a review round.
- After a rebase, replies that cite a SHA point at nothing — cite what changed (file, one
  line) alongside the commit, and resolve every thread you handled; an unresolved handled
  thread is what the next round re-raises.

## 4. Loop or stop

After each round, decide. The signals below are facts the round report carries, not
impressions; the report names which one fired.

**Request another round only if** the round implemented something substantive (new logic,
changed behavior, refactors — not typo/comment fixes) **and** none of the stop conditions
below holds. Then go to step 1 for the reviewers whose feedback prompted changes (in
auto-review repos the push already triggered it).

**Stop — the reviewer has finished with the PR** when any of:
- **Second-order round:** the round has at least one line-anchored finding — **suppressed
  comments included** — and every one of
  them sits on a review-fix commit (provenance from `kreview`: none on the original diff,
  none unknown). The reviewer has nothing left to say about the PR and is now reviewing the
  previous round. Disposition and implement the round as usual — a defect in a fix is still
  a defect — then **this is the last round**: do not re-request. The fix commits since the
  last review get a `kselfreview <last-reviewed-sha>..HEAD` pass instead of another paid
  round (the range is the argument, never the bare form, which would sweep in the working
  tree); that is what covers
  the one real risk of stopping here, an unreviewed fix. If `kselfreview` is not available
  where the loop runs, the report says so, names the unreviewed fix commits, and the verdict
  is ⚠️ needs human decision — never merge-ready. Measured: this fires at the 6th of
  14 Copilot reviews on devops-ai #27 and the 7th of 11 on homelab #18. Provenance that
  `kreview` reports as unknown (blame failed, no *reachable* submitted review, a review
  commit missing from the clone, unrelated commit) never
  fires this rule — an unknown is not a second-order finding. A rebase resets the boundary
  to the first review on the new history, so the round after a rebase reads as first-order
  and cannot end the loop by itself.
- **No in-scope IMPLEMENT items:** the round's findings were all push-backs, out-of-scope
  (now issues), repeats, or nitpicks.
- Reviewers returned no new findings, or approved. A round of review-level remarks with no
  line-anchored finding counts as no new findings — and **a suppressed comment is a
  line-anchored finding**, not a remark: it carries a `path:line`. Only a remark with no
  `path:line` anywhere is unanchored. Reading a body's summary prose and skipping its
  `Suppressed comments` section is how seven rounds on #49 looked like nothing was said.
- New comments only re-raise points already handled — reply linking the prior reasoning
  (kreview's cross-round memory), then stop. Copilot is *documented* to repeat comments on
  re-review even when threads were resolved or dismissed — the disposition ledger is the only
  defense, and "same findings twice" is the fixed point that means done.

**Stop — escalate** when any of:
- **A `systemic` finding whose root cause sits on pinned Surface** — anything the brief or
  the spec pins. `kreview` returns it as DISCUSS with the root cause named and lists it
  under *For the human*; this loop reads that as a stop signal, not as an item to
  implement. Buying another round here buys the next site of the same mechanism: #49's
  rounds 6–11 were five correct patches to five echo sites of one root cause, and the
  class was only named afterwards, as #60. Off pinned Surface a `systemic` finding does
  not stop the loop — `kreview` closes it as one class fix in one commit, or files one
  issue for the class — but **per-site patches across rounds are never the answer**; if a
  round's findings are the same mechanism it already patched last round, that is this stop.
  A PR with no brief pins no Surface, so on one of those this stop can only fire the second
  way: not on the first systemic finding, but on the round that repeats the last one's
  mechanism.
- **Round budget reached** (default 3 full rounds, `max-rounds:` raises it). Non-convergence
  within the budget means the disagreement is real; grinding won't fix it. The budget is the
  human's money; raising it changes **only** the budget — scope, provenance, and the
  second-order rule apply exactly as before. "Remove the cap and keep going" read as "run
  until zero findings" is how one loop reached round 13.
- Open **DISCUSS** items exist that block merge-readiness.
- CI can't be brought green within the loop's scope.

**Stopping is a state, not a mood.** Once the report (step 5) is posted, this session
requests no further review on this PR. Continuing takes the human's explicit words in this
session, and when they come, every rule in this step still applies. A loop that posted
"stopping here" and then ran eight more rounds before merge is the failure this sentence
exists for. At most **one** unrequested review is still owned after the stop: the one an
auto-review fires on the `kselfreview` fix push. Triage it under the same rules, append to
the report, do not re-request. If that triage pushes again and yet another review arrives,
it is listed in the report as unread, for the human — otherwise the chain never ends.

**Re-entry: every road back in goes through `/kbabysit <n>`.** Once a report is posted, any
further review round on this PR — **from any seat and for any reason**: new commits, a
relayed finding, a human decision, a fresh reviewer — is started by invoking
`/kbabysit <n>`, never by requesting a review directly. The re-invocation is what decides
between a paid round and a `kselfreview` pass, and it re-applies **every stop rule in this
step** — scope, provenance, second-order, systemic, DISCUSS — to the rounds it runs.

**One exception, the one that already existed:** the single unrequested auto-review that
fires on the `kselfreview` fix push is triaged in place and appended to the posted report,
as the paragraph above says. It is not a re-entry, because nobody requested it and nothing
follows it — the rule there is *do not re-request*, and that rule still ends the chain.
Anything beyond that one review is a re-entry and goes through `/kbabysit <n>`.

Concretely:

- An executor that is handed findings **with dispositions already attached** does not act
  on the relay. It runs `/kbabysit <n>` and lets the triage happen where the stop rules
  live. A disposition arriving from outside is somebody else's triage with no scope
  judgement, no provenance, and no budget attached to it.
- The observer seat has no re-request verb at all (`kobserve`): `/kbabysit <n>` or a
  question to the human, nothing else.
- Unreviewed fix commits after a posted report are covered by `kselfreview`, per the
  second-order stop above — they are not a reason to buy a round. **Step 0b is where that
  is executed**, before step 1 can spend anything; a rule with no branch in the procedure
  is a rule the next run walks straight past.

This is the narrow reading of *stopping is a state*: new commits are a legitimate trigger;
the trigger **re-enters the loop, it does not bypass it.** Measured on 2026-09-13: #49 and
#51 stopped correctly under this skill after 3 and 2 rounds, then ran 20 more paid Copilot
reviews in a phase that never invoked it — 25 reviews in total, 20 of them outside every
rule on this page.

Rounds are counted per babysit run, and a re-invocation on the same PR inherits thread
history (kreview reads prior replies, so push-backs stay remembered) and the same review
scope. **Be honest about what the budget does and does not bound:** each re-entry gets its
own budget, so re-entering repeatedly can spend more than `max-rounds` in total. Three
things bound the sequence instead, and none of them is a cumulative cap:

- **Re-entry needs an explicit trigger** — the human's words, or new commits someone
  pushed. It is never the loop's own idea.
- **Every stop rule fires inside each re-entry**, second-order and systemic included. That
  is precisely what the 20-round phase lacked: not a cap, but any rule at all.
- **The count is visible.** Every report states the paid rounds in *this* run and the
  running total on the PR, so a sequence that is growing is growing where the human can
  see it rather than inside a loop that reset its own counter.

A cumulative hard cap was considered and dropped by Karl as item 7 of the #61 list —
"not needed once 3 holds", 3 being the observer's loss of its re-request verb. If
re-entries start stacking up in practice, that decision is the thing to revisit, and it is
his to revisit; this skill does not quietly impose the cap he declined.

## 5. Report

Post the final report as a PR comment (durable record) **and** present it in chat:

```markdown
## Babysit report — PR #N

**TL;DR:** <2-3 sentences: rounds run, "N of M findings pushed back, N out of scope",
what materially improved, final state — merge-ready / needs decision on X / blocked on Y.>

**Verdict:** ✅ merge-ready (converged: <signal>) | ⚠️ needs human decision (stopped: <signal>) | ❌ blocked (<reason>)

### Rounds
| Round | Reviewers | Effort | Findings | Suppressed | On original diff | On fix commits | Unknown | Unanchored | Systemic | Implemented | Pushed back | Out of scope | Discuss | Commits |
|-------|-----------|--------|----------|------------|------------------|----------------|---------|------------|----------|-------------|-------------|--------------|---------|---------|

The four provenance columns sum to Findings. Unknown is its own column because it is what
keeps the second-order stop from firing, and Unanchored because it is excluded from that
stop; a report that hides either cannot show a human why a stop was safe. **Effort** is the
level the reviewer reported for that round (`Lite`/`Balanced`/`—`), so the "deeper first
pass" question has data instead of opinion. **Suppressed** is how many of that round's
line-anchored findings came from a review body's `Suppressed comments` section rather than
a thread — it is a subset of Findings, not a fifth provenance column, and a report where it
is always 0 on a Copilot loop is a report whose triage did not read the bodies.
**Systemic** counts the round's findings whose root cause covered a class.

### What changed because of review
- <material improvement, one line each — the value the loop added>

### Pushed back (with reasoning available in-thread)
- <gist — link to thread>

### Out of scope → issues
- <gist — issue link — which scope outcome it does not serve>

### Open for you (DISCUSS)
- <decision needed + the trade-off, enough context to decide without scrolling back>

### Systemic root causes
- <root cause — on pinned Surface (yours to decide) / closed as one class fix in <sha> /
  filed as #<issue> — one line each; "none found" if none>

**Why the loop stopped:** <second-order round / no in-scope IMPLEMENT / no new findings /
repeats / systemic on pinned Surface / budget / DISCUSS blocks / CI — one line naming the signal>
**Push-backs:** N of M findings · **CI:** green/red · **Merge conflicts:** none/yes
**Reviewer effort level:** <Lite/Balanced — and if Lite, that raising it is a repository
setting the human owns: Settings → Copilot → Code review → "Review effort level">
**Fix commits since last review:** <shas> · **kselfreview on them:** done / n/a
**Paid rounds:** N this run · N total on this PR (all runs) — the second number is the one
that grows across re-entries, and there is no cumulative cap on it by design (#61 item 7).
**Re-entry:** further rounds on this PR go through `/kbabysit <n>` — from any seat, for any
reason — which re-applies every stop rule in step 4.
```

**The verdict is a function of the stop, not of the to-do list.** ✅ follows a
*convergence* signal only — approved, no new findings, repeats-only, no in-scope
IMPLEMENT, or a second-order round whose fix commits got their `kselfreview` pass. Every
other stop — round budget, DISCUSS open, systemic on pinned Surface, or a round that
repeated last round's mechanism — is ⚠️ with the signal named in the verdict line itself,
even when nothing is left for the human to decide: the reviewer was still finding
first-order things when the loop chose to stop, and "nothing open for you" is not the
same sentence as "the reviewer is done with this PR". ❌ is CI red or conflicts the loop
could not clear — never ⚠️, because a branch whose gates are red is not a decision the
human can make.

**When more than one signal fires, ✅ needs all of them to be convergence signals — with
one exception, which has to be named in the line.** A budget reached on a round that also
converged was not the binding constraint, since the loop would have stopped anyway; it
does not downgrade the verdict, and the line says so (#66's report got this right: "the
budget was not the binding constraint: 2 of 3 rounds used"). Anything else firing
alongside does downgrade it, because the two claims conflict — a second-order round that
is *also* this round's repeat of last round's mechanism is a reviewer finding echo sites
inside the fixes, not a reviewer that is done with the PR.

Measured 2026-09-14: #66 and #75 wrote ✅ over a `systemic — same mechanism as last round`
stop, and #77 wrote ✅ over a round that was second-order but had both the budget and that
same systemic repeat firing with it. The human merged nothing and asked why he kept being
told a PR was ready when it was not; the answer was that this line used to be a menu with
no rule.

The "what changed" section is the honest measure of the loop: if it's empty after round 1,
say so — that's a signal the pre-PR gates are doing their job, not a failure of the loop.

The **push-back count is reported, never gated.** A PR can legitimately draw only true
findings. But many findings and zero push-backs across a run is a loop where judgement was
not exercised, and the human should see that number without asking: one runaway loop
pushed back 3 of 25 findings (all in its last round), the other 0 of about 65.

---

## Guardrails

- **Never merge.** Merge-ready is the finish line; the human merges.
- **Never force-push** during the loop — it orphans review threads.
- **Never trigger a Claude review.** No `@claude` comments on the PR, no `@claude review`,
  no subscribing, no re-enabling or re-running Claude review workflows — these are expensive
  and have caused runaway costs. If one fires anyway from leftover automation, triage its
  output like any other comments, but flag the still-active automation in the report.
- **Rounds cost real money** — Copilot reviews burn credits/Actions minutes. The round budget
  is a budget control, not just a convergence heuristic; don't spend a round on a re-review
  nothing warranted.
- **True is not the same as in scope.** A real defect outside the PR's review scope is an
  issue with a link, never a commit on this branch. The loop that implemented every true
  finding rewrote a registry's concurrency model inside a contract-prose PR.
- **One kind of change per PR** is hygiene, not a gate: both runaway loops mixed prose with
  code. In one the prose converged by round 4 and every later round landed on the code; in
  the other the late rounds reviewed a deploy procedure embedded in a plan document. If a
  PR mixes them, expect it, and let the scope block name which outcomes the code serves.
- Timebox waiting (step 2); a stalled reviewer never blocks the report.
- If the same reviewer flip-flops across rounds (suggests X, then suggests reverting X),
  freeze that file's feedback as DISCUSS and note the oscillation in the report.
- A budget exhausted without convergence is information, not an obstacle to push through —
  stop and hand the human a crisp decision.
