---
name: kreview
description: Address PR review comments critically — assess each comment, recommend action (implement/push-back/discuss), and execute. Works with any reviewer (Copilot, Claude, human).
metadata:
  version: "0.1.0"
---

# Address PR Review Comments

Use when a PR has review comments that need addressing — after pushing code, when checking automated feedback, or when a human reviewer has left comments.

## Core Principle: Critical Assessment First

Review comments — especially from automated reviewers — vary widely in quality. Assess each comment critically before acting. Your job is to decide whether each suggestion actually improves the code, not to implement every suggestion.

---

## Fetch All Review Comments

Reviews come from two different GitHub APIs. Check both:

```bash
PR_NUMBER=$(gh pr view --json number -q '.number' 2>/dev/null)
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')

# 1. Inline review comments (line-specific, from Copilot or human reviewers)
gh api "repos/$REPO/pulls/$PR_NUMBER/comments" \
  --jq '.[] | {user: .user.login, file: .path, line: .line, body: .body}'

# 2. General PR comments (not attached to lines)
gh api "repos/$REPO/issues/$PR_NUMBER/comments" \
  --jq '.[] | {user: .user.login, body: .body}'
```

`gh pr view --comments` only shows issue comments, not inline review comments — use both API calls above.

Fetch the full `.body` content. Review comments can be 2000+ characters with important details in later sections.

---

## Assess Each Comment

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

**DISCUSS** when the comment:
- Involves architectural decisions needing human input
- Presents valid trade-offs where both options are reasonable

---

## Assessment by Comment Type

**Code style** ("rename X to Y", "could be more concise"): Usually push back unless the current name is genuinely confusing.

**Assertions/tests** ("combine these", "simplify"): Often push back — separate assertions give better failure messages.

**Error handling** ("handle case where X is null"): Assess whether this is a real scenario. Don't add defensive code for impossible cases.

**Documentation** ("add a docstring"): Implement if the code is genuinely unclear. Push back if the code is self-documenting.

**Security** ("validate input X"): Implement if at a trust boundary. Push back if internal code where input is already validated.

**Performance** ("optimize by..."): Push back unless there's evidence of a real performance problem.

---

## Multiple Reviewers

When a PR has comments from multiple reviewers, compare them to identify signal:

- **Both flag the same issue**: high confidence it matters — likely implement
- **Only one flags it**: could be preference or a real issue — assess on merits
- **They contradict each other**: needs human judgment — discuss with user

Generate a comparison table showing overlap, unique concerns per reviewer, and contradictions with your recommendation.

## Reviewer Tendencies

**Copilot** tends to suggest combining intentionally separate code, flag "redundancy" that's actually clarity, and miss project-specific patterns.

**LLM-based reviewers** can be over-thorough, suggest documentation where code is self-documenting, and sometimes provide positive feedback that shouldn't be taken as comprehensive validation.

**Human reviewers** are better at architectural concerns and team conventions. Their style preferences carry more weight since they maintain the code.

---

## After Processing

1. Present a summary table: comment, reviewer, assessment, and action (IMPLEMENT/PUSH BACK/DISCUSS)
2. Ask whether to proceed with implementing valuable changes and drafting push-back responses
3. After implementing: commit, push, run tests and quality checks, post push-back responses
4. Advise whether to request re-review

Quality over compliance — a clean review with 0 comments addressed can be better than implementing bad suggestions. When pushing back, always explain your reasoning.
