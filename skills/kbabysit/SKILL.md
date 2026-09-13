---
name: kbabysit
description: Drive a PR from ready-for-review to merge-ready — request Copilot review, wait for it, triage and address comments via kreview against the PR's written review scope, re-request, and stop when the reviewer has finished with the PR (not with the fixes). Ends with a TL;DR report. Never merges, never triggers Claude reviews.
context: fork
agent: general-purpose
background: false
model: claude-opus-5
metadata:
  version: "0.3.0"
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

## How this runs — forked, on Opus

This skill's frontmatter carries `context: fork`, `agent: general-purpose`,
`background: false` and `model: claude-opus-5`, so the loop always executes in a subagent
on an Opus-grade model, never inline on the invoking session's model. Two reasons, both
measured: **tier economics** — babysitting is polling plus bounded per-finding judgement,
well within Opus-grade capability, and the invoking session's tier belongs to the
intent/acceptance decisions this loop feeds, not to a re-review poll; and **context
hygiene** — a run generates a lot of low-value output (poll results, review bodies, CI
logs) that stays in the subagent instead of silting up a long-lived design or
orchestration session. On 2026-09-03/04 the loop ran inline on a top-tier session because
the skill named no execution tier (agent-memory #246, recorded in devops-ai #25); Karl
observed the same thing again on 2026-09-12 and re-signed the rule, which is why the tier
is now in the frontmatter rather than in prose anyone can skip.

What that costs you, and how this skill pays it:

- **The fork sees no conversation history** — only this file with `$ARGUMENTS` substituted.
  So the PR number must either be passed explicitly (`/kbabysit 42`) or be resolvable from
  the checkout, which step 0 does with `gh pr view`. The fork starts in the invoking
  session's working directory (verified 2026-09-12), so a branch-derived PR resolves
  correctly; if `gh pr view` finds no PR, say so and stop rather than guessing.
- **`background: false`** makes the invoking turn wait for the report instead of collecting
  it from a background task later. The ownership rule below — an unread review round is not
  done — is the reason: a report that lands as a background notification after the session
  moved on is exactly the unread round. It also makes interactive runs behave like `-p`
  and SDK runs, which wait regardless. It needs Claude Code v2.1.218 or later; on an older
  build the field is inert and the fork reports back as a background task instead — later,
  but not lost.
- **`kreview` runs inside this subagent**, per round, and is not itself forked — forking it
  would hide each round's reasoning from the loop that has to decide whether to run another
  one. Invoke it with the Skill tool (available to a `general-purpose` fork, verified
  2026-09-12); if that tool is missing wherever this runs, read and follow
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

```bash
PR_NUMBER=$(gh pr view --json number -q '.number')   # or the <pr-number> from the arguments line above
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
gh pr view "$PR_NUMBER" --json state,isDraft,mergeable,headRefName,baseRefName,statusCheckRollup
```

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
  - **Claude reviews are out of scope — cost.** They are expensive and have caused runaway
    costs; they're meant to be unplugged from these repos. If you find Claude review
    automation still wired up (an `anthropics/claude-code-action` workflow on `pull_request`
    events, or a "Claude Code Review" check run appearing), don't touch it — but **flag it
    prominently in the final report** so the human can unplug it for real.

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

While waiting, also watch CI for the same head SHA — a red check that local gates missed is
round feedback exactly like a review comment, and it gets fixed in the same round.

On timeout, proceed with whatever arrived and record the no-show in the report — don't stall
the loop on a reviewer that never comes.

## 3. Triage and address — one kreview round

Run `kreview` in **autonomous mode** for this round. It fetches the full review surface
(review bodies, threads with resolved/outdated state, issue comments, CI), gives each new
finding its **provenance** (on the PR's original diff, or on a review-fix commit) and one of
four dispositions — IMPLEMENT / PUSH BACK / DISCUSS / OUT OF SCOPE — implements what's real
and in scope with gates green, files an issue for each out-of-scope finding, replies to every
thread, resolves handled ones, pushes, and returns a round report.

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
- **Second-order round:** the round has at least one line-anchored finding and every one of
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
  line-anchored finding counts as no new findings.
- New comments only re-raise points already handled — reply linking the prior reasoning
  (kreview's cross-round memory), then stop. Copilot is *documented* to repeat comments on
  re-review even when threads were resolved or dismissed — the disposition ledger is the only
  defense, and "same findings twice" is the fixed point that means done.

**Stop — escalate** when any of:
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

Rounds are counted per babysit run; a re-invocation on the same PR starts fresh but inherits
thread history (kreview reads prior replies, so push-backs stay remembered) and the same
review scope.

## 5. Report

Post the final report as a PR comment (durable record) **and** present it in chat:

```markdown
## Babysit report — PR #N

**TL;DR:** <2-3 sentences: rounds run, "N of M findings pushed back, N out of scope",
what materially improved, final state — merge-ready / needs decision on X / blocked on Y.>

**Verdict:** ✅ merge-ready | ⚠️ needs human decision | ❌ blocked

### Rounds
| Round | Reviewers | Findings | On original diff | On fix commits | Unknown | Unanchored | Implemented | Pushed back | Out of scope | Discuss | Commits |
|-------|-----------|----------|------------------|----------------|---------|------------|-------------|-------------|--------------|---------|---------|

The four provenance columns sum to Findings. Unknown is its own column because it is what
keeps the second-order stop from firing, and Unanchored because it is excluded from that
stop; a report that hides either cannot show a human why a stop was safe.

### What changed because of review
- <material improvement, one line each — the value the loop added>

### Pushed back (with reasoning available in-thread)
- <gist — link to thread>

### Out of scope → issues
- <gist — issue link — which scope outcome it does not serve>

### Open for you (DISCUSS)
- <decision needed + the trade-off, enough context to decide without scrolling back>

**Why the loop stopped:** <second-order round / no in-scope IMPLEMENT / no new findings /
repeats / budget / DISCUSS blocks / CI — one line naming the signal>
**Push-backs:** N of M findings · **CI:** green/red · **Merge conflicts:** none/yes
**Fix commits since last review:** <shas> · **kselfreview on them:** done / n/a
```

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
