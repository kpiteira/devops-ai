---
name: kobserve
description: The observer seat of the v2 contract — launch an executor session for a milestone, verify a delivered milestone PR before the human merges (independent blocking re-run, the "For the human" gate), and land it (spec row on main, teardown). Use when a signed feature needs its executors launched, a milestone PR needs verifying, or a merged milestone needs landing.
argument-hint: "launch <feature>/M<N> | verify <pr-number> | land <pr-number>"
metadata:
  version: "0.2.0"
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

1. **Worktree, session, and — where the project has one — sandbox, in one step**,
   with an explicit group:
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
   is coming. If provisioning fails on secrets, the slot stays allocated and
   `kinfra sandbox start` retries the sandbox — but no session was created (kinfra
   stops before that step), and `kinfra impl` will not run again on the existing
   worktree, so create the session by hand once the sandbox is up:
   ```bash
   agent-deck add <worktree-path> -t <feature>/M<N> -g <project>
   agent-deck session start <feature>/M<N>
   agent-deck session send <feature>/M<N> '/kbuild <feature>/M<N>'
   ```
2. **Kickoff: brief + environment facts only.** `kinfra impl --session` sends
   `/kbuild <feature>/M<N>` to the new session (bounded: kinfra's agent-deck calls time
   out after 60 s rather than hang, and kinfra says so if the kickoff was not
   delivered — then send it yourself). Where the project has a sandbox, follow with one
   message carrying its facts (`kinfra status` **run inside the executor's worktree**,
   the path `kinfra impl` printed — from the observer's checkout it reports no
   sandbox: slot, ports) — sent from the
   background, since `agent-deck session send` blocks while the target is busy; a
   project without a sandbox has no such facts and the brief's Working environment is
   the whole environment. Nothing the harness
   already sets: no attribution trailers, no model names; the executor's harness owns
   those and a conflicting kickoff is noise it has to resolve (pilot, 2026-09-11). The
   brief's Working environment carries the gates; the kickoff does not restate them.
3. **Verify the session started on the executor tier** (status bar), then leave it
   alone. A parked question from an executor is a defect to fix in tooling or brief,
   not a reason to sit with it — note it for the planner.
4. **Never share a checkout with a child.** The observer touches the project's
   repository only through a temporary, detached worktree it creates and removes — git
   refuses a second worktree on a branch that is already checked out, so detach and
   push explicitly. Main takes no direct pushes (ruleset since 2026-09-14, #28: pull
   request required, `check` and `integration` required, no bypass), so bookkeeping
   lands one of two ways:
   - **On the milestone PR itself, before the human merges it** — the default. The
     spec's Decomposition row (`delivered (PR #N)`) and any fact-correction amendment
     are one commit on the PR branch, pushed from a detached worktree at the branch
     tip; the merge carries them, so the row is true exactly when the commit that
     holds it is on main. No second PR, no second Copilot review.
     ```bash
     SCRATCH=$(mktemp -d)
     git -C <repo> fetch origin <pr-branch>
     git -C <repo> worktree add --detach "$SCRATCH/pr-bookkeeping" origin/<pr-branch>
     # …edit, commit…
     git -C "$SCRATCH/pr-bookkeeping" push origin HEAD:<pr-branch>
     git -C <repo> worktree remove "$SCRATCH/pr-bookkeeping"
     ```
     A non-fast-forward here means the executor pushed again — its loop re-entered:
     fetch, rebase, retry once; if the branch moves again, wait for the loop to stop.
     The executor's checkout is then behind its own branch; its next push fetches.
   - **On a branch and PR of its own** when nothing is open to ride on (an amendment
     the human acknowledged after the merge, a roadmap line). Every PR to main draws
     an automatic Copilot review, so batch such edits rather than opening one per line.
     ```bash
     git -C <repo> worktree add --detach "$SCRATCH/bookkeeping" origin/main
     # …edit, commit…
     git -C "$SCRATCH/bookkeeping" push origin HEAD:refs/heads/bookkeeping/<slug>
     gh pr create --head bookkeeping/<slug> --title "spec(<feature>): <what>" \
       --body-file <file carrying a "## Review scope" section: the one bookkeeping outcome>
     ```
     The human merges it when `check` and `integration` are green, like any PR.
   The worktree is removed only after the push landed; on a conflict or a dead
   network it stays, with the commit in it, and nothing is torn down.
   The pilot's observer once switched the checkout a triage planner was working in;
   staged edits rode along.

## verify

**In:** a milestone PR with the mapping line `Spec: … · Milestone: M<N>`, CI green,
review rounds converged (`kbabysit` report present).

**This seat has no re-request verb.** It never requests or re-requests a Copilot (or any)
review, never runs `kreview`, and never sends an executor a finding with a disposition
attached. Its only two moves in a PR's review loop are to send the executor
`/kbabysit <n>` — which carries every stop rule and does its own triage — or to put a
question to the human. Unreviewed fix commits after a posted babysit report are covered by
`kselfreview`, by `kbabysit`'s own rule; they are not a reason to buy a round. Measured
2026-09-13: this seat relayed pre-decided dispositions to two executors and re-requested
Copilot each round, and 20 of the 25 paid Copilot reviews on #49 (13) and #51 (12) were
spent in that phase — outside `kbabysit`, with no budget, no provenance and no stop rules,
after both loops had already stopped correctly at 3 and 2 rounds (#61).

Three things that phase got wrong, each one a rule now:

- **A disposition is triage, and triage belongs to the seat that pays for it.** Sending
  `(1) FIX … (2) IMPLEMENT …` makes the executor a typist: no scope judgement, no
  provenance, no isolated-or-systemic question, no round budget.
- **Re-requesting is spending.** A re-request from here bypasses the budget that exists
  precisely to stop a loop that a reviewer will otherwise never end.
- **A relay per round is a hand-rolled loop with no stop rules.** If the loop needs to
  continue, the thing that continues it is `/kbabysit <n>`, because that is where stopping
  is defined.

Findings this seat genuinely notices — from the independent re-run, the guard, the spec
diff — do **not** open a third path to the executor. They go in the PR thread as the
observation itself (where they are public, and where the executor's next `/kbabysit <n>`
picks them up as review surface like any other comment), or to the human as a question.
The message sent to an executor is still only ever `/kbabysit <n>`. "What is wrong, without
what to do about it" sounds safer than a disposition and is not: it arrives out of band,
carries no scope judgement, provenance or budget, and the executor acts on it anyway —
which is the relay failure under a politer name.

1. **Independent re-run.** From a seat that is not the executor's — your own checkout
   of the PR head, or a sandbox you provision — run the brief's `blocking:` command
   and compare with the PR body's pasted output: same head, same count. Until the CI
   wiring in the evolutions backlog lands, this is what "verifiable by a stranger"
   means in practice. Record the command and output in a PR comment.
2. **Guard.** If the project's contract-integrity guard did not run (not deployed, or
   the PR predates it), run it by hand: the *script* comes from the base commit, the
   *diff* it judges is `<base>...HEAD`, so run it in a checkout of the PR head:
   ```bash
   git worktree add --detach "$SCRATCH/pr-head" origin/<pr-branch>
   git -C "$SCRATCH/pr-head" show <base>:.devops-ai/check_contract_integrity.py > "$SCRATCH/guard.py"
   (cd "$SCRATCH/pr-head" && python3 "$SCRATCH/guard.py" <base> <pr-branch>)
   ```
   The guard covers briefs and the acceptance tree only; `SPEC.md` is not guard-
   protected, so diff it yourself: only the Decomposition status row and its
   Evidence may have changed. Anything else in the spec from an `impl/*` branch is
   a divergence to hand to `/kspec triage`.
3. **The "For the human" gate.** Read the PR's three sections. *Decisions I made
   alone*: sanity-read, note anything that looks like a product semantic misfiled.
   *Facts I corrected*: verify each against main; if one changed what was built, it is
   a divergence — stop and hand to `/kspec triage`; otherwise append each as a
   pre-checked fact-correction amendment to the spec **on the PR branch** (the
   bookkeeping route above), in the same commit that sets the Decomposition row to
   `delivered (PR #N)` — the merge makes both true at once.
   *For the human*: put every item to
   the human **before merge**, options-first — fix now (a `replan` for this milestone)
   or defer to the feature close — and never argue the executor's case. Record his
   answers in the PR thread. The pilot's "silence is a miss" reached him three exchanges
   after merge because nobody owned this step.
4. **Report:** merge-ready, with the re-run evidence and his answers — or blocked, with
   the reason. He merges.

## land

**In:** the human merged the PR.

1. Confirm the Decomposition row landed with the merge (`delivered (PR #N)`, pushed
   to the PR branch at verify). If it did not, it goes on a bookkeeping branch and PR
   (the second route in `launch` step 4), batched with anything else pending.
2. Tear down: `kinfra done <feature>-M<N>` (stops containers, removes the slot's
   volumes, releases the slot, removes the agent-deck session, removes the worktree).
3. If a dependent milestone is now unblocked and no amendment is pending, `launch` it.
   If the feature's last milestone merged, tell the human it is ready for
   `/kspec close` in a fresh session.

## Guardrails

- Never merge; never decide a product semantic; never edit a brief or an acceptance
  test (planner branches only).
- **Never request a review, never run `kreview`, never relay a disposition.** The two
  review-loop moves are `/kbabysit <n>` to the executor and a question to the human. This
  one cost 20 paid Copilot rounds on 2026-09-13 (#61).
- Never resolve a *For the human* item by reasoning about it — it is a question, not a
  finding.
- Model checked at every start and restart; group passed at every launch; no checkout
  shared with a child. Each of these cost the pilot a round.
