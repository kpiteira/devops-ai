---
name: kloop
description: Execute one milestone task per fresh context — the loop body for autonomous runs. Verification is the gate; this file only sequences.
metadata:
  version: "0.1.0"
---

# kloop — the loop body

One invocation = one task. The enforcement lives in the verifier (`make check`,
the task's Verify command, the blocking Stop hook) — deliberately not in this file.

```
/kloop [milestone file]
```

## The loop body

1. Read the milestone file (the argument, or the file with unchecked tasks under
   the configured design path). Read the HANDOFF file next to it.
2. Take the **first open task** (`## [ ] Task N.M`). None left → report the
   milestone state (all `[x]`, or `[!]` blockers awaiting Karl) and stop.
3. Search for prior art before writing anything new — extend the existing mechanism
   or say in the handoff why you couldn't.
4. Do the task as written (STRUCTURE and VALIDATION tasks carry their own
   instructions). For code: TDD — failing tests first, then make the task's
   **Verify** command and `make check` both exit 0. Never weaken a test, a gate,
   or a threshold to get green.
5. Flip the checkbox to `[x]` and append one evidence line under the heading:
   the Verify command and its result tail.
6. Add to the handoff only what the next task needs (gotchas, not status). Commit:
   conventional message naming the task ID.
7. Stop. The next task gets a fresh context.

## Escalate instead of grinding

Escalating flips the checkbox to `[!]` (blocked — a human decides) with a one-line
reason under the heading, so the loop moves on instead of re-grinding it:

- **The design fights the task** (third workaround against the same contract,
  pattern that doesn't fit) → write an ACP (`templates/acp.md`), mark `[!]`, stop.
- **A gate or Verify command looks wrong** → mark `[!]` with why. Editing
  thresholds, contracts, or ratchets is Karl's call (`structural-gates` rule).
- **Three failed attempts on one task** → mark `[!]`, record what was tried and
  why it failed, stop.

## Driving the loop

The milestone file is the goal state; "done" is checkboxes plus a green gate —
never the agent's claim.

- **Shell loop (true fresh context per task, Ralph-style):** the file itself is
  the loop condition — it terminates when every task is `[x]` or `[!]`:

  ```sh
  M=docs/designs/<feature>/implementation/M2_x.md
  while grep -q '## \[ \]' "$M"; do
    claude -p "/kloop $M" --permission-mode acceptEdits
  done
  ```
- **Goal mode (one session, evaluator-checked):**
  `/goal every task in docs/designs/<feature>/implementation/M2_x.md is checked [x] and make check exits 0`
  — fine for a few tasks; for long milestones prefer the shell loop (compaction
  degrades long sessions — state must live in the milestone file and git, not context).
- The kinfra-generated Stop hook blocks any turn from ending while `make check`
  is red, in both modes.
