---
name: kobserve
description: The observer seat of the v2 contract — launch an executor session for a milestone, verify a delivered milestone PR before the human merges (independent blocking re-run, the "For the human" gate), and land it (spec row on main, teardown). Use when a signed feature needs its executors launched, a milestone PR needs verifying, or a merged milestone needs landing.
argument-hint: "launch <feature>/M<N> | verify <pr-number> | land <pr-number>"
metadata:
  version: "0.1.0"
---

# kobserve — launch, verify, land

Between the human and the planner and executor sessions sits one seat that launches
each executor, verifies each delivery, and lands each merge. The v2 pilot ran it by
hand and the recipe below is what it learned. This is a planner-tier seat: it puts
product semantics in front of the human and never decides them.

```
/kobserve launch <feature>/M<N>    # executor session for one milestone
/kobserve verify <pr>              # before the human merges a milestone PR
/kobserve land <pr>                # after he merged it
```

**First, every mode:** say which model this session runs on and check every session
you start or resume — the session manager resumes on its default model after a restart,
and a child carries its parent's. A planner seat on the executor tier stops.

## launch

**In:** a signed spec (`Signed off` filled, no unchecked amendment) and a milestone
whose dependencies are `delivered`.

1. **Worktree, sandbox, session in one step**, with an explicit group:
   ```bash
   kinfra impl <feature>/M<N> --session --group <project>
   ```
   Always pass the group: a session added without one inherits its parent's, and
   groups default to a running-session cap of 1 — the parent counts — so the child
   queues and errors (pilot, 2026-09-06). Parallel milestones need a group whose cap
   allows them, or their own groups. Secret resolution is **silent while it waits**: a
   1Password approval prompt shows nothing from the human's seat and `kinfra impl`
   does not announce it (the announce-and-batch fix lives in `secret-providers`). So
   before launching, make sure the keychain is unlocked and the human knows an approval
   is coming; if provisioning fails on secrets, the slot stays allocated and
   `kinfra sandbox start` retries.
2. **Kickoff: brief + environment facts only.** `kinfra impl --session` sends
   `/kbuild <feature>/M<N>` to the new session; follow it with one message carrying
   the sandbox's facts (`kinfra status`: slot, ports) — sent from the background, since
   `agent-deck session send` blocks while the target is busy. Nothing the harness
   already sets: no attribution trailers, no model names; the executor's harness owns
   those and a conflicting kickoff is noise it has to resolve (pilot, 2026-09-11). The
   brief's Working environment carries the gates; the kickoff does not restate them.
3. **Verify the session started on the executor tier** (status bar), then leave it
   alone. A parked question from an executor is a defect to fix in tooling or brief,
   not a reason to sit with it — note it for the planner.
4. **Never share a checkout with a child.** The observer touches the project's main
   checkout only through a temporary, detached worktree it creates and removes — git
   refuses a second worktree on a branch that is already checked out, so detach and
   push explicitly:
   ```bash
   SCRATCH=$(mktemp -d)
   git -C <repo> fetch origin main
   git -C <repo> worktree add --detach "$SCRATCH/main-bookkeeping" origin/main
   # …edit, commit…
   git -C "$SCRATCH/main-bookkeeping" push origin HEAD:main
   git -C <repo> worktree remove "$SCRATCH/main-bookkeeping"
   ```
   The pilot's observer once switched the checkout a triage planner was working in;
   staged edits rode along.

## verify

**In:** a milestone PR with the mapping line `Spec: … · Milestone: M<N>`, CI green,
review rounds converged (`kbabysit` report present).

1. **Independent re-run.** From a seat that is not the executor's — your own checkout
   of the PR head, or a sandbox you provision — run the brief's `blocking:` command
   and compare with the PR body's pasted output: same head, same count. Until the CI
   wiring in the evolutions backlog lands, this is what "verifiable by a stranger"
   means in practice. Record the command and output in a PR comment.
2. **Guard.** If the project's contract-integrity guard did not run (not deployed, or
   the PR predates it), run it by hand from the base commit:
   ```bash
   git show <base>:.devops-ai/check_contract_integrity.py > /tmp/guard.py && python3 /tmp/guard.py <base> <branch>
   ```
   Only the spec's status row may have changed among planner-owned files.
3. **The "For the human" gate.** Read the PR's three sections. *Decisions I made
   alone*: sanity-read, note anything that looks like a product semantic misfiled.
   *Facts I corrected*: verify each against main; if one changed what was built, it is
   a divergence — stop and hand to `/kspec triage`; otherwise append each as a
   pre-checked fact-correction amendment to the spec on `main` (the bookkeeping
   worktree above) now, so the signed spec is true before the merge, not after.
   *For the human*: put every item to
   the human **before merge**, options-first — fix now (a `replan` for this milestone)
   or defer to the feature close — and never argue the executor's case. Record his
   answers in the PR thread. The pilot's "silence is a miss" reached him three exchanges
   after merge because nobody owned this step.
4. **Report:** merge-ready, with the re-run evidence and his answers — or blocked, with
   the reason. He merges.

## land

**In:** the human merged the PR.

1. Through the bookkeeping worktree, set the spec's Decomposition row to `delivered`
   with the merge commit in Evidence (unless the executor's PR already did), commit,
   push.
2. Tear down: `kinfra done <feature>-M<N>` (stops containers, removes the slot's
   volumes, releases the slot, removes the agent-deck session, removes the worktree).
3. If a dependent milestone is now unblocked and no amendment is pending, `launch` it.
   If the feature's last milestone merged, tell the human it is ready for
   `/kspec close` in a fresh session.

## Guardrails

- Never merge; never decide a product semantic; never edit a brief or an acceptance
  test (planner branches only).
- Never resolve a *For the human* item by reasoning about it — it is a question, not a
  finding.
- Model checked at every start and restart; group passed at every launch; no checkout
  shared with a child. Each of these cost the pilot a round.
