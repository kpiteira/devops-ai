---
name: kbabysit
description: Drive a PR from ready-for-review to merge-ready — request Copilot review, wait for it, triage and address comments via kreview, re-request, and loop until another round adds no value. Ends with a TL;DR report. Never merges, never triggers Claude reviews.
metadata:
  version: "0.1.0"
---

# kbabysit — babysit a PR to merge-ready

Orchestrates the review loop for one PR: request reviews → wait → triage/address (via
`kreview`) → decide on re-review → repeat. The loop ends when reviewing stops adding value,
not when reviewers stop talking — an empty round and a round of pure nitpicks both mean done.

```
/kbabysit                # PR for the current branch
/kbabysit <pr-number>
/kbabysit <pr-number> max-rounds: 5
```

**End state:** merge-ready (or explicitly blocked) + a detailed report with TL;DR. This skill
never merges and never closes a DISCUSS item on its own — those are the human's calls.

---

## 0. Preflight

```bash
PR_NUMBER=${ARG:-$(gh pr view --json number -q '.number')}
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
gh pr view "$PR_NUMBER" --json state,isDraft,mergeable,headRefName,baseRefName,statusCheckRollup
```

- PR closed/merged → report and stop.
- Draft → mark ready (`gh pr ready`) only if the work is actually complete; otherwise stop.
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
(review bodies, threads with resolved/outdated state, issue comments, CI), triages each new
comment IMPLEMENT / PUSH BACK / DISCUSS, implements what's real with gates green, replies to
every thread, resolves handled ones, pushes, and returns a round report.

The babysitter's own rules on top:

- **Never weaken a test, gate, or threshold to satisfy a reviewer** — that's a DISCUSS with
  the human, not an implement.
- A reviewer comment that fights the architecture is an ACP-shaped question — escalate,
  don't loop on it.
- Keep the round's push to one coherent commit (or a few logical ones); in auto-review repos
  every push spends a review round.

## 4. Loop or stop

After each round, decide:

**Request another round only if** the round changed code substantively (new logic, changed
behavior, refactors — not typo/comment fixes). Then go to step 1 for the reviewers whose
feedback prompted changes (in auto-review repos the push already triggered it).

**Stop — converged** when any of:
- The round produced **zero IMPLEMENT items** (all feedback was push-backs, nitpicks, or
  repeats of prior rounds).
- Reviewers returned no new comments, or approved.
- New comments only re-raise points already handled — reply linking the prior reasoning
  (kreview's cross-round memory), then stop. Copilot is *documented* to repeat comments on
  re-review even when threads were resolved or dismissed — the disposition ledger is the only
  defense, and "same findings twice" is the fixed point that means done.

**Stop — escalate** when any of:
- **Round cap reached** (default 3 full rounds). Non-convergence after 3 rounds means the
  disagreement is real; grinding won't fix it.
- Open **DISCUSS** items exist that block merge-readiness.
- CI can't be brought green within the loop's scope.

Rounds are counted per babysit run; a re-invocation on the same PR starts fresh but inherits
thread history (kreview reads prior replies, so push-backs stay remembered).

## 5. Report

Post the final report as a PR comment (durable record) **and** present it in chat:

```markdown
## Babysit report — PR #N

**TL;DR:** <2-3 sentences: rounds run, what materially improved, final state —
merge-ready / needs decision on X / blocked on Y.>

**Verdict:** ✅ merge-ready | ⚠️ needs human decision | ❌ blocked

### Rounds
| Round | Reviewers | New comments | Implemented | Pushed back | Discuss | Commits |
|-------|-----------|--------------|-------------|-------------|---------|---------|

### What changed because of review
- <material improvement, one line each — the value the loop added>

### Pushed back (with reasoning available in-thread)
- <gist — link to thread>

### Open for you (DISCUSS)
- <decision needed + the trade-off, enough context to decide without scrolling back>

**Why the loop stopped:** <converged / cap / escalation — one line>
**CI:** green/red · **Merge conflicts:** none/yes
```

The "what changed" section is the honest measure of the loop: if it's empty after round 1,
say so — that's a signal the pre-PR gates are doing their job, not a failure of the loop.

---

## Guardrails

- **Never merge.** Merge-ready is the finish line; the human merges.
- **Never force-push** during the loop — it orphans review threads.
- **Never trigger a Claude review.** No `@claude` comments on the PR, no `@claude review`,
  no subscribing, no re-enabling or re-running Claude review workflows — these are expensive
  and have caused runaway costs. If one fires anyway from leftover automation, triage its
  output like any other comments, but flag the still-active automation in the report.
- **Rounds cost real money** — Copilot reviews burn credits/Actions minutes. The round cap is
  a budget control, not just a convergence heuristic; don't spend a round on a re-review
  nothing warranted.
- Timebox waiting (step 2); a stalled reviewer never blocks the report.
- If the same reviewer flip-flops across rounds (suggests X, then suggests reverting X),
  freeze that file's feedback as DISCUSS and note the oscillation in the report.
- Three rounds without convergence is information, not an obstacle to push through — stop and
  hand the human a crisp decision.
