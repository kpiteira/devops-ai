---
name: kreview
description: Address PR review comments critically — assess each comment against the PR's written review scope, recommend action (implement/push-back/discuss/out-of-scope), and execute. Works with any reviewer (Copilot, human, other bots). Single-round engine; kbabysit drives the multi-round loop.
metadata:
  version: "0.4.0"
---

# Address PR Review Comments

Use when a PR has review comments that need addressing — after pushing code, when checking
automated feedback, or when a human reviewer has left comments. One invocation processes one
round of review; `/kbabysit` invokes this repeatedly to drive a PR to merge-ready.

## Core Principle: Critical Assessment First

Review comments — especially from automated reviewers — vary widely in quality. Assess each
comment critically before acting. Your job is to decide whether each suggestion actually
improves **this PR**, not to implement every suggestion. Quality over compliance — a round
where zero comments get implemented (all pushed back with reasoning) can be the correct
outcome. And true is not the same as in scope: a real defect the PR was never for is an issue,
not a commit (see OUT OF SCOPE below). Two loops on 2026-09-12 implemented nearly every
finding and ran 13 and 11 rounds, most of them fixing things the PR did not exist to fix.

## Modes

- **Attended** (default): present the triage table, get confirmation, then act.
- **Autonomous** (`/kreview auto`, or when invoked by `kbabysit`): act on IMPLEMENT,
  PUSH BACK and OUT OF SCOPE without asking. DISCUSS items are never resolved autonomously —
  reply to the thread with the trade-off, leave it open, and list it in the round report for
  the human.

---

## 1. Fetch the Full Review Surface

Feedback lives in four places. A partial fetch produces a partial triage — get all four:

```bash
PR_NUMBER=$(gh pr view --json number -q '.number')
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')

# 1. Reviews (state + summary bodies — some reviewers put their findings here)
gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/reviews" \
  --jq '.[] | {id, user: .user.login, state, submitted_at, body}'

# 2. Review threads with state (new vs resolved vs outdated) — GraphQL only.
#    --paginate follows pageInfo automatically, so >100 threads aren't silently dropped.
#    Per-thread comments are capped at the first 100 (the API max) — a longer thread than
#    that isn't a review, it's a meeting; escalate it rather than paginating deeper.
gh api graphql --paginate -f query='
  query($owner:String!, $repo:String!, $pr:Int!, $endCursor:String) {
    repository(owner:$owner, name:$repo) { pullRequest(number:$pr) {
      reviewThreads(first:100, after:$endCursor) {
        nodes {
          id isResolved isOutdated path line
          comments(first:100) { nodes { databaseId url author{login} body createdAt
                                        originalLine originalCommit { oid } } }
        }
        pageInfo { hasNextPage endCursor }
      }}}}' -f owner="${REPO%/*}" -f repo="${REPO#*/}" -F pr="$PR_NUMBER"

# 3. General PR comments (not attached to lines)
gh api --paginate "repos/$REPO/issues/$PR_NUMBER/comments" \
  --jq '.[] | {id, user: .user.login, body}'

# 4. CI state (a red check is feedback too)
gh pr checks "$PR_NUMBER" 2>/dev/null || true
```

`gh pr view --comments` only shows issue comments — never rely on it alone. Fetch full
`.body` content; review comments can be 2000+ characters with the key detail in later sections.

**Suppressed comments are findings.** Copilot folds part of its output into a
`### Suppressed comments (N)` section of the **review body** instead of opening threads —
each entry a line `**path:line**` followed by the finding text and often a code snippet.
They are not a lesser class of finding, and a triage that reads only threads is blind to
them: on devops-ai #49, 15 suppressed entries appeared across 11 of the 13 Copilot
reviews, while only **4** of those 13 reviews opened a thread at all — and from round 6
(14:27) on, 7 of the last 8 opened none, so 8 of the 9 findings that whole phase produced
existed only in the bodies. Parse them out:

````bash
# --paginate runs the --jq filter per page, so emit a marker line per review and let awk
# carry that review's commit_id down its body. The fence toggle stops a `**path:line**`
# line *inside* a quoted snippet from being counted as a finding of its own.
gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/reviews" \
  --jq '.[] | select(.state != "PENDING") | "@@REVIEW\t\(.id)\t\(.commit_id)", (.body // "")' \
| awk -F'\t' '
    $1=="@@REVIEW" { rid=$2; sha=$3; sup=0; fence=0; next }
    /^```/         { fence=!fence; next }
    fence          { next }
    /^#+ +Suppressed comments/     { sup=1; next }
    sup && /^- \*\*Files reviewed/ { sup=0 }
    sup && /^\*\*[^*]+:[0-9]+\*\*$/ {
      s=substr($0,3,length($0)-4); p=s; sub(/:[0-9]+$/,"",p); l=s; sub(/^.*:/,"",l)
      print rid"\t"sha"\t"p"\t"l }'
# one row per suppressed finding: review-id · the commit the review judged · path · line
````

**Zero rows is an ambiguous negative** — it means "no suppressed comments", "no reviews",
*or* "the parse broke", and those are not the same thing. Never read it as the first. The
headers declare their own counts, so make the parse check itself:

```bash
gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/reviews" --jq '.[] | .body // ""' \
  | grep -oE '^#+ +Suppressed comments \([0-9]+\)' | grep -oE '[0-9]+' \
  | awk '{n += $1} END {print "declared: " n+0}'
```

Parsed must equal declared. A mismatch is a defect in the parser (GitHub changed the
format), never an empty round — say so and triage from the bodies by hand for that round.

Measured on devops-ai #49 (2026-09-13): 15 parsed, 15 declared, across the 11 headers; the
two Copilot reviews with no header — an approval, and a round whose single finding *did*
open a thread — correctly yield none.

Each row is a **line-anchored finding** and is triaged like any other. Two differences,
both mechanical:

- **Provenance is computed the same way**, with the review's own `commit_id` standing in
  for `originalCommit.oid` and the parsed line for `originalLine` in the snippet below.
  Suppressed findings are included in the provenance counts, so `kbabysit`'s second-order
  stop sees them: a round whose line-anchored findings — suppressed ones included — all
  sit on fix commits is that reviewer's last round. On #49 that stop would have fired at
  round 6 instead of round 13: its only two findings were suppressed, at
  `azurekeyvault.py:245` and `:160`, and blaming both at the review's own commit
  (`70a8f107`) against the boundary (`5a9b106d`, the first review still in the history)
  puts them on `23ee88a2` and `63465ed7` — two review-fix commits. Seven paid rounds went
  to findings the loop already had the rule to stop on, and could not see.
- **There is no thread to reply in.** The disposition goes in the round report (which is
  posted as a PR comment, so the record is durable and public), and an IMPLEMENT names
  the finding in the fix commit message. Nothing to resolve, so nothing is resolved.

**The review scope.** The PR body carries a `## Review scope` section — the outcomes this
PR delivers, in the author's words (`kbabysit` refuses to start without it; attended runs
should ask for it rather than infer one). Read it before triaging: it is the reference every
disposition below is judged against, and what lets a stranger check the judgement later.

```bash
gh pr view "$PR_NUMBER" --json body -q '.body' | sed -n '/^## Review scope/,/^## /p'
```

**Provenance of each finding.** A line-anchored finding sits either on the PR's original
diff or on a *review-fix commit* (anything pushed after the first review was submitted).
This is a fact about commits, computed, not judged, and `kbabysit` reads it to decide
whether the reviewer is still reviewing the PR or has moved on to reviewing the fixes:

```bash
# Boundary of the original diff: the head the earliest review (any reviewer) was submitted
# against *that is still in the current history*. A rebase gives every commit a new SHA, so
# reviews from before it are skipped and the first review on the new history becomes the
# boundary. --paginate runs the jq filter per page ("first" would be per-page too), so emit
# every submitted review and pick in the shell (gh rejects --slurp together with --jq).
# Run on the PR branch checkout: HEAD must be the PR head, or nothing is an ancestor.
# A review commit the clone does not have is fetched by SHA first (GitHub serves commits it
# still holds, pre-rebase ones included) and then judged like any other: a pre-rebase commit
# is a non-ancestor and is skipped; only a commit the remote cannot serve is MISSING, which
# the provenance check maps to unknown — is-ancestor alone cannot tell the two apart.
REVIEWS=$(gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/reviews" \
  --jq '.[] | select(.state != "PENDING") | "\(.submitted_at) \(.commit_id)"' | sort)
FIRST_REVIEWED_SHA=$(printf '%s\n' "$REVIEWS" | while read -r ts sha; do
      [ -n "$sha" ] || continue
      git cat-file -e "$sha^{commit}" 2>/dev/null || git fetch -q origin "$sha" 2>/dev/null \
        || { echo "MISSING $sha"; break; }
      git merge-base --is-ancestor "$sha" HEAD && { echo "$sha"; break; }
    done)
# Boundary status for the round report: sha | none (no reviews) | none reachable (N reviews,
# all pre-rebase) | missing <sha>


# Per finding: blame at the commit the comment was made against (originalCommit.oid,
# originalLine from the thread fetch; for a suppressed finding, the review's own commit_id
# and the line parsed out of its `**path:line**` header) — never at the current head, where
# a later fix that touched the line would claim it and every old finding would look
# second-order.
BLAME_SHA=$(git blame -L "$ORIGINAL_LINE,$ORIGINAL_LINE" --porcelain "$ORIGINAL_COMMIT" -- "$FILE" \
  2>/dev/null | head -1 | cut -d' ' -f1)
if [ -z "$FIRST_REVIEWED_SHA" ]; then
  [ -z "$REVIEWS" ] && echo "unknown (no submitted review yet)" \
    || echo "unknown (no reachable submitted review: $(printf '%s\n' "$REVIEWS" | wc -l | tr -d ' ') reviews, all pre-rebase)"
elif [ "${FIRST_REVIEWED_SHA#MISSING}" != "$FIRST_REVIEWED_SHA" ]; then
  echo "unknown (review commit ${FIRST_REVIEWED_SHA#MISSING } not in this clone: git fetch --unshallow, or fetch the PR head)"
elif [ -z "$BLAME_SHA" ]; then echo "unknown (blame failed: git fetch origin pull/$PR_NUMBER/head)"
elif git merge-base --is-ancestor "$BLAME_SHA" "$FIRST_REVIEWED_SHA"; then echo "original diff"
elif git merge-base --is-ancestor "$FIRST_REVIEWED_SHA" "$BLAME_SHA"; then echo "review-fix commit"
else echo "unknown (not in this PR's history: unrelated commit)"; fi
```

Three states, never two, and "review-fix" only for a commit that **descends** from the
first reviewed head: a failed blame, a missing boundary, or a commit on neither side of it
is **unknown**. A poller that cannot tell "I could not look" from "it is on a fix" would
stop loops by accident. A rebase resets the boundary rather than breaking it: reviews whose
commit is no longer in the current history are skipped, so the first post-rebase review
becomes the boundary and every line-anchored finding it raises reads as original — that
round can never be second-order, which costs at most one round (the runaway loops cost ten).
Until that first post-rebase review is submitted the boundary is empty ("no reachable
submitted review"), which is not the same as "no review": the round report's **Boundary**
line carries which. `kbabysit` still
forbids force-pushing mid-loop, for the threads' sake. A line that pre-dates the PR blames to an
ancestor of the first reviewed head too, so it counts as original: the reviewer is still
looking at first-order code (scope decides whether it is this PR's). Only a finding with
**no line at all** — a review-level remark, an issue comment — is unanchored and has no
provenance; a suppressed comment carries a `path:line` and is anchored like any thread.
Measured on
devops-ai #27: the 6th of 14 Copilot reviews was the first whose findings all sat on fix
commits, and from the 9th on every review was entirely second-order; the 8th still found a
real first-order defect, a generated test that raised before asserting.

**Scope to what's actionable:** skip threads that are `isResolved`, and skip `isOutdated`
threads unless the underlying concern plainly still applies to the current code. On a repeat
round, process only comments newer than the round you last handled (compare `createdAt` /
`submitted_at` against the previous round's timestamp).

---

## 2. Assess Each Comment

| Question | If yes... |
|----------|-----------|
| Does fixing it serve an outcome in the PR's Review scope? | If **no**: OUT OF SCOPE, whatever its truth — stop assessing here |
| Does this fix a real bug? | High value — likely implement |
| Does this improve readability or maintainability significantly? | Medium value — consider |
| Is this a style nitpick with no functional benefit? | Low value — likely push back |
| Could this suggestion make things worse? | Push back with reasoning |
| Does the reviewer lack context for this suggestion? | Discuss or push back |

### Before the disposition: isolated or systemic?

Every finding gets one question **before** it gets a verdict, because the answer changes
the verdict: **does a deeper change close the class this finding belongs to?** The answer
goes in its own column of the disposition table, as `isolated` or `systemic → <root cause>`.

- **isolated** — the finding is the whole of its class. Patch it and the class is gone.
- **systemic → \<root cause\>** — the finding is one site of a mechanism that has others.
  Naming the root cause *is* the work: a `systemic` verdict with no root cause named is an
  `isolated` one wearing a label.

A `systemic` verdict then forces one of exactly two moves, and the pinned Surface decides
which:

- **On pinned Surface** — anything the brief or the spec pins — it is **DISCUSS**, with the
  root cause named, listed under *For the human* in the round report. Not implemented site
  by site, and not implemented as a class fix either: changing pinned Surface is the
  human's decision, not a round's. `kbabysit` reads it as a stop signal and escalates
  rather than buying the next round.
- **Off the pinned Surface** — either the class fix **in one commit**, or **one issue
  naming the class** (one issue for the class, never one per site). Per-site patches
  spread across rounds are the failure this column exists to prevent.

Measured (#61, from PR #49): rounds 6–11 were five patches to five echo sites of a single
root cause — unvalidated `akv://` segments echoed back into `az` error text. Every patch
was correct; none was the fix; round 12 was clean only because the echo sites ran out; the
class was filed afterwards as #60. One `systemic → unvalidated segments reach the error
text` in round 6 would have bought that outcome for one round instead of six.

Two findings in the same round that share a mechanism are one `systemic` row with one root
cause, not two `isolated` rows that happen to rhyme.

## Categorize: IMPLEMENT / PUSH BACK / DISCUSS / OUT OF SCOPE

Scope is decided first, on one question: **does fixing this serve an outcome named in the
PR's Review scope?** Only a yes reaches the other three. Code this PR added to deliver an
outcome is in scope, defects in it included; code the PR touched on the way, or added in an
earlier round for a finding that was itself outside the scope, is not. The finding being
true, severe, or easy does not move it in.

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
- Is `systemic` and its root cause sits on pinned Surface (above) — name the root cause,
  not the site

**OUT OF SCOPE** when fixing it serves no outcome in the Review scope. It becomes an issue,
never a commit on this branch — including when the finding is a real defect. The reply names
the scope outcome it does not serve, so the reviewer (and the human) can disagree with the
call rather than with silence.

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
15–25%): a comment that can't cite verifiable behavior gets pushed back, briefly. Some
reviewers pre-tag severity — trust the tag as a prior, not a verdict. Positive summary
feedback from an LLM reviewer is not comprehensive validation; it means that reviewer found
nothing, not that nothing is there.

### Cross-round memory

Before triaging, read your own prior replies on the PR (your comments in the thread fetch).
If a new comment re-raises something already pushed back on or filed as out of scope, don't
re-litigate or re-file: reply with a link to the prior reasoning or the issue and move on.
Flip a prior push-back to IMPLEMENT only if the new comment brings a genuinely new argument —
oscillating on the same point is worse than either choice.

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
| IMPLEMENT | "Fixed in `<sha>`" + one line on what changed (the line is what survives a rebase) | Resolve the thread |
| PUSH BACK | Your reasoning, concretely — never a bare "won't fix" | Resolve the thread |
| DISCUSS | The trade-off and what you'd need to decide | Leave open for the human |
| OUT OF SCOPE | "Real, but outside this PR's scope (<which outcome it doesn't serve>) — filed as #<issue>" | File the issue, then resolve the thread |

```bash
# OUT OF SCOPE: the issue carries the finding verbatim and a link back to the thread
# (the comment's `url` from the fetch). Reviewer text never goes through shell expansion —
# a finding quoting `$(...)` or backticks would execute — so it is written with printf '%s'.
BODY_FILE=$(mktemp)
{
  printf 'Raised by %s on #%s (%s), out of that PR review scope: serves none of <the scope outcomes>. Filed rather than fixed there.\n\n' \
    "$REVIEWER" "$PR_NUMBER" "$THREAD_URL"
  printf '%s\n' "$FINDING_BODY"
} > "$BODY_FILE"
gh issue create --title "<finding gist>" --body-file "$BODY_FILE"
```

Resolving push-backs is deliberate: the reasoning is preserved in the thread and surfaced in
the round report, and leaving them open just makes the merge-time skim noisier. Know what
resolving does and doesn't do: it's hygiene for humans — Copilot is documented to repeat
comments on re-review even when threads were resolved or dismissed (your prior replies are
the real memory), and bots don't read thread replies at all.
Review-level bodies and issue comments have no thread to resolve — address their points in the
round report, and reply on the PR only if a point needs a visible answer. **Suppressed
comments have no thread either**, but unlike a review-level remark they carry a `path:line`
and a verdict: their dispositions go in the round report row by row, and an IMPLEMENT names
the finding in the fix commit message so the trail survives without a thread.

Push the commit(s) after replies are posted. Note: in repos with review automation, a push may
itself trigger the next review round — that's `kbabysit`'s concern, not yours.

---

## 4. Round Report

End every invocation with this report (in autonomous mode it's the return value `kbabysit`
consumes):

```markdown
## Review round report — PR #N, round R
**Reviewers heard from:** copilot, ... · **Comments processed:** X new (Y skipped: resolved/outdated)
**Reviewer effort level:** <as the review body reports it, e.g. Lite | Balanced | not reported>

| # | Reviewer | File:Line | Source | Provenance | Comment (gist) | Isolated/systemic | Verdict | Action taken |
|---|----------|-----------|--------|------------|----------------|-------------------|---------|--------------|

`Source` is `thread` or `suppressed` — both are line-anchored, and the difference only
decides where the reply goes. `Isolated/systemic` is never blank: `isolated`, or
`systemic → <root cause>`.

**Boundary:** <sha> | none (no reviews) | none reachable (N reviews, all pre-rebase) | missing <sha>
**Provenance:** N on original diff · N on review-fix commits · N unknown · N unanchored — of the line-anchored, N from threads and N suppressed
**Implemented:** N (commit <sha>) · **Pushed back:** N · **Out of scope → issues:** N (#…) · **Discuss (open for human):** N
**Systemic:** N (N on pinned Surface → for the human, N closed as a class fix, N filed as one issue)
**For the human — systemic on pinned Surface:** <root cause + what pins the Surface, one line each | none>
**Gates:** tests ✓/✗ · quality ✓/✗ · CI ✓/✗
**Re-review recommended:** yes/no — <one line why>
```

Recommend re-review only when the round changed code beyond trivia (a typo-level fix doesn't
need another full review). A round of pure push-backs never needs re-review — there's nothing
new to look at. The provenance line is not yours to act on: `kbabysit` reads it, and a round
with nothing on the original diff is the reviewer's last round whatever you recommend. The
systemic lines are the same kind of fact: a systemic root cause on pinned Surface ends the
loop whatever you recommend, because the next round would only find the next site.
