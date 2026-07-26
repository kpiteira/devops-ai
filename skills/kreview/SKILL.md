---
name: kreview
description: Address PR review comments critically — assess each comment, recommend action (implement/push-back/discuss), and execute. Works with any reviewer (Copilot, Claude, human). Single-round engine; kbabysit drives the multi-round loop.
metadata:
  version: "0.2.0"
---

# Address PR Review Comments

Use when a PR has review comments that need addressing — after pushing code, when checking
automated feedback, or when a human reviewer has left comments. One invocation processes one
round of review; `/kbabysit` invokes this repeatedly to drive a PR to merge-ready.

## Core Principle: Critical Assessment First

Review comments — especially from automated reviewers — vary widely in quality. Assess each
comment critically before acting. Your job is to decide whether each suggestion actually
improves the code, not to implement every suggestion. Quality over compliance — a round where
zero comments get implemented (all pushed back with reasoning) can be the correct outcome.

## Modes

- **Attended** (default): present the triage table, get confirmation, then act.
- **Autonomous** (`/kreview auto`, or when invoked by `kbabysit`): act on IMPLEMENT and
  PUSH BACK without asking. DISCUSS items are never resolved autonomously — reply to the
  thread with the trade-off, leave it open, and list it in the round report for the human.

---

## 1. Fetch the Full Review Surface

Feedback lives in four places. A partial fetch produces a partial triage — get all four:

```bash
PR_NUMBER=$(gh pr view --json number -q '.number')
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')

# 1. Reviews (state + summary bodies — Claude Code Review puts its findings here)
gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/reviews" \
  --jq '.[] | {id, user: .user.login, state, submitted_at, body}'

# 2. Review threads with state (new vs resolved vs outdated) — GraphQL only
gh api graphql -f query='
  query($owner:String!, $repo:String!, $pr:Int!) {
    repository(owner:$owner, name:$repo) { pullRequest(number:$pr) {
      reviewThreads(first:100) { nodes {
        id isResolved isOutdated path line
        comments(first:50) { nodes { databaseId author{login} body createdAt } }
      }}}}}' -f owner="${REPO%/*}" -f repo="${REPO#*/}" -F pr="$PR_NUMBER"

# 3. General PR comments (not attached to lines)
gh api --paginate "repos/$REPO/issues/$PR_NUMBER/comments" \
  --jq '.[] | {id, user: .user.login, body}'

# 4. CI state (a red check is feedback too)
gh pr checks "$PR_NUMBER" 2>/dev/null || true
```

`gh pr view --comments` only shows issue comments — never rely on it alone. Fetch full
`.body` content; review comments can be 2000+ characters with the key detail in later sections.

**Scope to what's actionable:** skip threads that are `isResolved`, and skip `isOutdated`
threads unless the underlying concern plainly still applies to the current code. On a repeat
round, process only comments newer than the round you last handled (compare `createdAt` /
`submitted_at` against the previous round's timestamp).

---

## 2. Assess Each Comment

| Question | If yes... |
|----------|-----------|
| Does this fix a real bug? | High value — likely implement |
| Does this improve readability or maintainability significantly? | Medium value — consider |
| Is this a style nitpick with no functional benefit? | Low value — likely push back |
| Could this suggestion make things worse? | Push back with reasoning |
| Does the reviewer lack context for this suggestion? | Discuss or push back |

## Categorize: IMPLEMENT / PUSH BACK / DISCUSS

**IMPLEMENT** when the comment:
- Fixes actual bugs or security issues
- Significantly improves clarity
- Adds missing error handling that matters

**PUSH BACK** when the comment:
- Is a style nitpick with no functional benefit
- Reduces debuggability (e.g., combining assertions loses failure context)
- Over-engineers for hypothetical scenarios
- Contradicts project patterns
- Re-raises something already pushed back on in a prior round (see Cross-Round Memory)

**DISCUSS** when the comment:
- Involves architectural decisions needing human input
- Presents valid trade-offs where both options are reasonable

### Assessment by comment type

**Code style** ("rename X to Y", "could be more concise"): Usually push back unless the current name is genuinely confusing.

**Assertions/tests** ("combine these", "simplify"): Often push back — separate assertions give better failure messages.

**Error handling** ("handle case where X is null"): Assess whether this is a real scenario. Don't add defensive code for impossible cases.

**Documentation** ("add a docstring"): Implement if the code is genuinely unclear. Push back if the code is self-documenting.

**Security** ("validate input X"): Implement if at a trust boundary. Push back if internal code where input is already validated.

**Performance** ("optimize by..."): Push back unless there's evidence of a real performance problem.

### Multiple reviewers

When a PR has comments from multiple reviewers, compare them to identify signal:

- **Both flag the same issue**: high confidence it matters — likely implement
- **Only one flags it**: could be preference or a real issue — assess on merits
- **They contradict each other**: needs human judgment — discuss

Automated reviewers lack project history and still miss cross-file/architectural issues;
human reviewers' style preferences carry more weight since they maintain the code. Don't
discount a comment by its source — a bot regularly catches real logic errors — but expect a
real noise floor (independent evaluations put Copilot's vague/false-positive rate around
15–25%): a comment that can't cite verifiable behavior gets pushed back, briefly. Managed
Claude review pre-tags severity (🔴 Important / 🟡 Nit / 🟣 Pre-existing) — trust it as a
prior, not a verdict. Positive summary feedback from an LLM reviewer is not comprehensive
validation; it means that reviewer found nothing, not that nothing is there.

### Cross-round memory

Before triaging, read your own prior replies on the PR (your comments in the thread fetch).
If a new comment re-raises something already pushed back on, don't re-litigate: reply with a
link to the prior reasoning and move on. Flip a prior push-back to IMPLEMENT only if the new
comment brings a genuinely new argument — oscillating on the same point is worse than either
choice.

---

## 3. Act

**IMPLEMENT items:** make the change with tests (per the `tdd` rule where it applies), then
run the project's unit tests and quality checks from `.devops-ai/project.md`. All gates green
per the `quality-gates` rule before committing. One commit for the round is fine; reference
what it addresses.

**Every non-skipped thread gets a reply.** Unanswered comments are what make later rounds
noisy — the reviewer (or re-review) can't tell handled from ignored:

```bash
# Reply to an inline review thread (use the comment's databaseId)
gh api "repos/$REPO/pulls/$PR_NUMBER/comments/$COMMENT_ID/replies" -f body="..."

# Resolve a thread after replying (use the GraphQL thread id)
gh api graphql -f query='
  mutation($id:ID!) { resolveReviewThread(input:{threadId:$id}) { thread { isResolved } } }' \
  -f id="$THREAD_ID"
```

| Verdict | Reply with | Then |
|---------|-----------|------|
| IMPLEMENT | "Fixed in `<sha>`" + one line on what changed | Resolve the thread |
| PUSH BACK | Your reasoning, concretely — never a bare "won't fix" | Resolve the thread |
| DISCUSS | The trade-off and what you'd need to decide | Leave open for the human |

Resolving push-backs is deliberate: the reasoning is preserved in the thread and surfaced in
the round report, and leaving them open just makes the merge-time skim noisier. Know what
resolving does and doesn't do: it's hygiene for humans — Copilot is documented to repeat
comments on re-review even when threads were resolved or dismissed (your prior replies are
the real memory), and bots don't read thread replies at all. One exception: on PRs where
managed Claude review is push-subscribed, leave Claude's fixed threads for Claude — its next
run auto-resolves what's actually fixed, which doubles as verification.
Review-level bodies and issue comments have no thread to resolve — address their points in the
round report, and reply on the PR only if a point needs a visible answer.

Push the commit(s) after replies are posted. Note: in repos with review automation, a push may
itself trigger the next review round — that's `kbabysit`'s concern, not yours.

---

## 4. Round Report

End every invocation with this report (in autonomous mode it's the return value `kbabysit`
consumes):

```markdown
## Review round report — PR #N, round R
**Reviewers heard from:** copilot, claude[bot] · **Comments processed:** X new (Y skipped: resolved/outdated)

| # | Reviewer | File:Line | Comment (gist) | Verdict | Action taken |
|---|----------|-----------|----------------|---------|--------------|

**Implemented:** N (commit <sha>) · **Pushed back:** N · **Discuss (open for human):** N
**Gates:** tests ✓/✗ · quality ✓/✗ · CI ✓/✗
**Re-review recommended:** yes/no — <one line why>
```

Recommend re-review only when the round changed code beyond trivia (a typo-level fix doesn't
need another full review). A round of pure push-backs never needs re-review — there's nothing
new to look at.
