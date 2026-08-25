---
name: kissue
description: Implement GitHub issues using TDD. Fetches the issue, creates a branch, implements with RED/GREEN/REFACTOR, and opens a PR with "Closes #N".
metadata:
  version: "0.2.0"
---

# Issue Implementation Command

Implements GitHub issues end-to-end: fetch issue, create branch, research, implement with TDD, verify, and open a PR.

## Command Usage

```
/kissue <issue-number>
/kissue                    # List open issues and pick one
```

---

## 1. Fetch Issue

```bash
gh issue view <number> --json title,body,labels,state,assignees
```

- If issue is closed: note it and confirm whether to proceed
- If issue has a linked PR: note it and confirm whether to continue

When called without an issue number, list open issues and ask which one to implement:
```bash
gh issue list --state open --limit 10 --json number,title,labels,updatedAt
```

## 2. Setup Branch

Create a branch from the issue:

```bash
git checkout -b issue-<number>-<slug>
```

The slug is the issue title lowercased, spaces replaced with hyphens, truncated to ~40 chars, non-alphanumeric removed.

## 3. Research

Get to where the issue holds no surprises: what it's actually asking, which files it touches, the
patterns this codebase uses for that kind of change, and any acceptance criteria in the body.
Scale this to the issue — a typo fix needs none of it; a new code path needs all of it. If the
issue's framing turns out to be wrong (the bug is elsewhere, a named file has moved), that's signal
worth surfacing before you code, not something to quietly work around.

## 4. Implement with TDD

Write the tests that prove the fix or feature — the `test-quality` rule is the bar (outcomes, not choreography; fakes at the seams).

If the issue has acceptance criteria, write tests that map to them.

## 5. Verify

Run unit tests and quality checks using project config commands. Validate each acceptance criterion from the issue.

## 6. Complete

Commit with a clear message referencing the issue. Use conventional prefixes (`fix:`, `feat:`, `refactor:`).

Push and create a PR:

```bash
git push -u origin issue-<number>-<slug>

gh pr create --title "<type>: <description>" --body "$(cat <<'EOF'
## Summary

[Brief description of the change]

## Changes

- [List of changes]

## Testing

- Unit tests: [count] added/modified
- Quality checks: passing

Closes #<issue-number>
EOF
)"
```

The `Closes #N` automatically links the PR and closes the issue on merge.

---

## Error Handling

| Blocker | Response |
|---------|----------|
| Tests won't pass | Investigate root cause, ask for help if unclear |
| Acceptance criteria ambiguous | Ask user for clarification |
| Scope larger than expected | Discuss splitting into multiple issues |
| Dependency on other work | Note dependency, ask whether to proceed or wait |

Don't create a PR with incomplete work. Document the blocker and ask for guidance.
