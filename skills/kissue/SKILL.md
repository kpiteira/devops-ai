---
name: kissue
description: Implement GitHub issues using TDD. Fetches the issue, creates a branch, implements with RED/GREEN/REFACTOR, and opens a PR with "Closes #N".
metadata:
  version: "0.1.0"
---

# Issue Implementation Command

Implements GitHub issues using TDD methodology. Handles the full lifecycle: fetch issue, create branch, implement, verify, and open a PR.

---

## Configuration Loading

**FIRST STEP — Do this before any workflow action.**

1. Read `.devops-ai/project.md` from the project root
2. If the file exists, extract:
   - **Project.name** — used in context and reporting
   - **Testing.unit_tests** — command to run unit tests
   - **Testing.quality_checks** — command to run quality checks
   - If essential values (Testing.*) are missing or say "Not configured": ask for them
   - If optional values (Infrastructure, E2E) are missing: skip those sections silently
3. If the file does NOT exist:
   - Ask: "What command runs your unit tests?" (default: `pytest tests/`)
   - Ask: "What command runs quality checks?" (default: none)
   - Suggest creating `.devops-ai/project.md` for future sessions
4. Use the configured values throughout this workflow

---

## Command Usage

```
/kissue <issue-number>
/kissue                    # List open issues and pick one
```

---

## Workflow

```
1. Fetch       → Get issue details from GitHub
2. Setup       → Create branch
3. Research    → Read issue, find affected code
4. Implement   → TDD cycle (RED → GREEN → REFACTOR)
5. Verify      → Unit tests, quality checks
6. Complete    → Create PR with "Closes #N"
```

---

### 1. Fetch Issue

```bash
# Get issue details
gh issue view <number> --json title,body,labels,state,assignees
```

**Checks:**
- If issue is closed: "Issue #N is already closed."
- If issue has a linked PR: "Issue #N already has PR #X. Continue anyway?"

**Display:**

```
## Issue #N: [Title]

**Labels:** bug, enhancement
**State:** open

**Description:**
[Issue body]
```

### No-Argument Mode

When called without an issue number:

```bash
# List open issues, most recent first
gh issue list --state open --limit 10 --json number,title,labels,updatedAt
```

Display them and ask which one to implement.

---

### 2. Setup

Create a branch from the issue:

```bash
# Generate branch name from issue number + title
# Example: issue-42-fix-login-timeout
git checkout -b issue-<number>-<slug>
```

The slug is the issue title lowercased, spaces replaced with hyphens, truncated to ~40 chars, non-alphanumeric characters removed.

---

### 3. Research

Before writing any code:

1. **Read the issue thoroughly** — Understand what's being asked
2. **Find relevant code** — Locate files mentioned or implied by the issue
3. **Identify patterns** — Find similar code for style and conventions
4. **Check for acceptance criteria** — Extract from issue body if present

**Output:** Brief summary (2-4 sentences) covering:
- What the issue is asking for
- Which files will be affected
- Implementation approach

Do not write implementation code during this phase.

---

### 4. Implementation (TDD)

Follow the TDD cycle: **RED → GREEN → REFACTOR**

#### RED: Write Failing Tests

1. Create test file(s) following project conventions
2. Write tests covering:
   - Happy path (normal operation)
   - Error cases (failures, exceptions)
   - Edge cases (boundaries, null values)
3. Run tests using the configured unit test command
4. Verify tests fail meaningfully (not import errors)

#### GREEN: Minimal Implementation

1. Write just enough code to make tests pass
2. Follow existing patterns in the codebase
3. Run tests frequently during implementation
4. Don't over-engineer or add untested features

#### REFACTOR: Improve Quality

1. Improve code clarity
2. Run unit tests + quality checks using configured commands
3. Ensure all checks pass

---

### 5. Verification

Run all quality gates:

```bash
# Unit tests (from project.md)
<configured unit_tests command>

# Quality checks (from project.md)
<configured quality_checks command>
```

Validate acceptance criteria from the issue:

```
- [x] Criterion 1 — VALIDATED
- [x] Criterion 2 — VALIDATED
```

All criteria must be met. If any fail, continue working before proceeding.

---

### 6. Completion

#### Commit Changes

Commit with a clear message referencing the issue:

```bash
git add <specific files>
git commit -m "fix: <description> (#<number>)"
```

Use conventional commit prefixes: `fix:`, `feat:`, `refactor:`, `docs:`, `test:` as appropriate.

#### Push and Create PR

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

## Acceptance Criteria

- [x] Criterion 1
- [x] Criterion 2

Closes #<issue-number>
EOF
)"
```

The `Closes #N` automatically links the PR and closes the issue on merge.

#### Task Summary

```
## Issue Complete: #N — [Title]

**What was implemented:**
- [Brief description]

**Files changed:**
- [List]

**Key decisions:**
- [Any non-obvious choices]

**Tests:**
- Unit: X tests added/modified
- Quality: passing

**PR:** <url>
```

---

## Error Handling

If blocked during implementation:

| Blocker | Response |
|---------|----------|
| Tests won't pass | Investigate root cause, ask for help if unclear |
| Acceptance criteria ambiguous | Ask user for clarification |
| Scope larger than expected | Discuss whether to split into multiple issues |
| Dependency on other work | Note the dependency, ask whether to proceed or wait |

Do not create a PR with incomplete work. Document the blocker and ask for guidance.

---

## Quick Reference

| Phase | Key Actions | Output |
|-------|-------------|--------|
| **Fetch** | Get issue, check state | Issue summary displayed |
| **Setup** | Create branch | `issue-N-slug` branch |
| **Research** | Read issue, find code | 2-4 sentence summary |
| **RED** | Write tests, verify fail | "Tests failing as expected" |
| **GREEN** | Implement, pass tests | "All tests passing" |
| **REFACTOR** | Clean up, quality | "Quality checks passing" |
| **Complete** | Push, create PR | PR link |
