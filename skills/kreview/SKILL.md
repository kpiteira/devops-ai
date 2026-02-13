---
name: kreview
description: Address PR review comments critically — assess each comment, recommend action (implement/push-back/discuss), and execute. Works with any reviewer (Copilot, Claude, human).
metadata:
  version: "0.1.0"
---

# Address PR Review Comments

Use when:
- A PR has review comments that need addressing
- User says "address review", "check PR comments", "handle review feedback"
- After pushing code and wanting to check for automated reviewer feedback

---

## Core Principle: Critical Assessment First

**DO NOT blindly implement every suggestion.** Review comments — especially from automated reviewers — vary widely in quality. Your job is to:

1. **Assess** each comment critically
2. **Decide** whether it improves the code
3. **Act** appropriately (implement, push back, or discuss)

---

## Configuration Loading

Read `.devops-ai/project.md` from the project root to get:
- **Testing.unit_tests** — command to run unit tests after changes
- **Testing.quality_checks** — command to run quality checks after changes

If no config exists, ask for these values.

---

## Workflow

### Step 1: Fetch ALL Review Comments

Reviews come from TWO different GitHub APIs. You must check BOTH:

```bash
# Get PR number and repo info from current branch
PR_NUMBER=$(gh pr view --json number -q '.number' 2>/dev/null)
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')

# 1. Inline review comments (line-specific, typically from Copilot or human reviewers)
gh api "repos/$REPO/pulls/$PR_NUMBER/comments" \
  --jq '.[] | {user: .user.login, file: .path, line: .line, body: .body}'

# 2. General PR comments (not attached to lines, sometimes from CI-triggered reviewers)
gh api "repos/$REPO/issues/$PR_NUMBER/comments" \
  --jq '.[] | {user: .user.login, body: .body}'
```

**DO NOT TRUNCATE**: Review comments can be 2000+ characters with important details in later sections. Always fetch the FULL `.body` content.

**Why two sources?**
- **Pull request review comments** (`/pulls/.../comments`): Comments attached to specific code lines during a review.
- **Issue comments** (`/issues/.../comments`): General PR-level comments not attached to specific lines.

> **Note:** `gh pr view --comments` only shows issue comments, not inline review comments. Use the API calls above to get both.

### Step 2: Assess Each Comment

For each comment, evaluate:

| Question | Assessment |
|----------|------------|
| Does this fix a real bug? | High value if yes |
| Does this improve readability significantly? | Medium value if yes |
| Does this improve maintainability? | Medium value if yes |
| Is this a style nitpick with no functional benefit? | Low value |
| Could this suggestion make things worse? | Negative value — push back |
| Is this context-dependent and the reviewer lacks context? | Discuss or push back |

### Step 3: Categorize

Assign each comment to one of:

#### IMPLEMENT
- Fixes actual bugs
- Prevents real security issues
- Significantly improves clarity
- Adds missing error handling that matters

#### PUSH BACK
- Style nitpicks with no functional benefit
- Suggestions that reduce debuggability (e.g., combining assertions)
- Over-engineering for hypothetical scenarios
- Changes that contradict project patterns
- Automated suggestions that lack context

#### DISCUSS
- Architectural decisions that need human input
- Trade-offs where both options are valid
- Changes that might affect other parts of the codebase

---

## Assessment Criteria by Comment Type

### Code Style Comments
```
"Consider renaming X to Y"
"This could be more concise"
```
**Usually PUSH BACK** unless the current name is genuinely confusing.

### Assertion/Test Comments
```
"Combine these assertions"
"Simplify this test"
```
**Often PUSH BACK** — Separate assertions give better failure messages. Don't sacrifice debuggability for brevity.

### Error Handling Comments
```
"Add error handling for X"
"Handle the case where Y is null"
```
**ASSESS carefully** — Is this a real scenario? Don't add defensive code for impossible cases.

### Documentation Comments
```
"Add a docstring"
"Document this behavior"
```
**IMPLEMENT** if the code is genuinely unclear. **PUSH BACK** if the code is self-documenting.

### Security Comments
```
"Validate input X"
"Sanitize before using"
```
**IMPLEMENT** if at a trust boundary. **PUSH BACK** if internal code where input is already validated.

### Performance Comments
```
"This could be optimized by..."
"Consider caching X"
```
**PUSH BACK** unless there's evidence of a real performance problem. Premature optimization is the root of all evil.

---

## Response Templates

### For IMPLEMENT
```
Implementing: [brief description]
Reason: [why this improves the code]
```
Then make the change.

### For PUSH BACK
Draft a response for the PR:
```
Thanks for the suggestion. Keeping the current implementation because:
- [Concrete reason 1]
- [Concrete reason 2]
```

### For DISCUSS
Ask the user:
```
Comment suggests: [summary]
Trade-offs:
- Option A: [pros/cons]
- Option B: [pros/cons]
How would you like to proceed?
```

---

## After Processing All Comments

Provide a summary:

```
## Review Assessment Summary

**PR**: #<number>
**Reviewers**: <list>
**Total comments**: N

| # | Reviewer | Comment | Assessment | Action |
|---|----------|---------|------------|--------|
| 1 | copilot | Combine assertions | Low value — loses debug info | PUSH BACK |
| 2 | alice | Add user feedback | Medium value — UX improvement | IMPLEMENT |
| 3 | copilot | Rename variable | Nitpick | PUSH BACK |

**Implementing**: N comments
**Pushing back**: N comments
**Discussing**: N comments

Shall I proceed with implementing the valuable changes and drafting push-back responses?
```

---

## Multiple Reviewers: Comparison

When a PR has comments from multiple reviewers, generate a comparison to identify signal:

```
## Reviewer Comparison: PR #<number>

### Overview
| Metric | Reviewer A | Reviewer B |
|--------|-----------|-----------|
| Total comments | 4 | 6 |
| High value | 1 | 3 |
| Low value/nitpicks | 3 | 2 |
| Overlapping concerns | 2 | 2 |

### Agreement (Both flagged)
Higher confidence these matter:
- [ ] Issue X: [brief description]

### Only Reviewer A
- [ ] [description] — Assessment: [IMPLEMENT/PUSH BACK/DISCUSS]

### Only Reviewer B
- [ ] [description] — Assessment: [IMPLEMENT/PUSH BACK/DISCUSS]

### Contradictions
Where reviewers disagree:
- A says: [X]
- B says: [Y]
- **Recommendation**: [which to follow and why]
```

### Interpreting Agreement/Disagreement

| Scenario | Interpretation | Action |
|----------|---------------|--------|
| Both flag same issue | High confidence it matters | Likely IMPLEMENT |
| Only one flags it | Could be preference or real issue | Assess on merits |
| They contradict | Need human judgment | DISCUSS with user |

---

## Common Automated Reviewer Patterns

### Copilot Tends To:
- Suggest combining code that's intentionally separate
- Flag "redundancy" that's actually clarity
- Miss project-specific patterns
- Suggest over-abstraction

### LLM-Based Reviewers May:
- Be context-aware but sometimes over-thorough
- Suggest documentation where code is self-documenting
- Sometimes miss that simpler is better
- Provide positive feedback that shouldn't be treated as comprehensive validation

### Human Reviewers:
- Better at architectural concerns
- May reference team conventions you should follow
- Style preferences carry more weight (they maintain the code)

---

## When Done

After addressing all comments:
1. Commit implemented changes
2. Push to update the PR
3. Post push-back responses as PR comments (or suggest user does)
4. Run unit tests and quality checks to confirm nothing is broken
5. Advise whether to request re-review

---

## Key Reminders

1. **Quality over compliance** — A clean review with 0 comments addressed can be better than implementing bad suggestions
2. **Explain push-backs** — Don't just ignore; respond with reasoning
3. **Trust your judgment** — You've read the code; automated reviewers often haven't
4. **Ask when uncertain** — Use DISCUSS for genuinely ambiguous cases
5. **Batch similar decisions** — If pushing back on multiple similar comments, explain once
