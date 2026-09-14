---
name: kobserve
description: The observer seat of the v2 contract — launch an executor session for a milestone, verify a delivered milestone PR before the human merges (independent blocking re-run, the "For the human" gate, the spec row committed onto the PR branch so the merge carries it), and land it (confirm the row landed, teardown). Use when a signed feature needs its executors launched, a milestone PR needs verifying, or a merged milestone needs landing.
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
   push explicitly. **Where main rejects direct pushes** — a branch ruleset requiring a
   pull request, as devops-ai has since 2026-09-14 (#28: PR required, `check` and
   `integration` required, no bypass) — bookkeeping lands one of two ways. This skill is
   installed globally across projects, so read that as a condition to check, not as a
   fact about every repo: where main is unprotected, a direct push from the same detached
   worktree is still the simplest route and the two below are the fallback.

     ```bash
     gh api "repos/$REPO/rules/branches/main" --jq '.[].type' | grep -qx pull_request
     ```
     That endpoint reports the rules actually **in force** on the branch, org-level
     rulesets included; a `pull_request` entry is this condition. Do not read
     `repos/$REPO/rulesets` for it — it lists the repo's own rulesets whatever their
     enforcement or target (devops-ai's has three, one `disabled`) and no org rules, so
     both its empty and its non-empty answers mean several things at once. Trying the
     push is the other unambiguous probe.
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
     pushed=false
     for attempt in 1 2; do
       if git -C "$SCRATCH/pr-bookkeeping" push origin HEAD:<pr-branch>; then pushed=true; break; fi
       git -C "$SCRATCH/pr-bookkeeping" fetch origin <pr-branch> \
         && git -C "$SCRATCH/pr-bookkeeping" rebase FETCH_HEAD || break
     done
     if [ "$pushed" = true ]; then
       git -C <repo> worktree remove "$SCRATCH/pr-bookkeeping"
     else
       echo "bookkeeping NOT pushed — worktree kept at $SCRATCH/pr-bookkeeping"; exit 1
     fi
     ```
     A non-fast-forward here means the executor pushed again — its loop re-entered, which
     is what the one retry is for; if the branch moves again the retry is spent, the
     worktree stays with the commit in it, and you wait for the loop to stop before
     re-running. The executor's checkout is then behind its own branch; its next push
     fetches.
   - **On a branch and PR of its own** when nothing is open to ride on (an amendment
     the human acknowledged after the merge, a roadmap line). Every PR to main draws
     an automatic Copilot review, so batch such edits rather than opening one per line.
     ```bash
     SCRATCH=$(mktemp -d)
     git -C <repo> fetch origin main
     git -C <repo> worktree add --detach "$SCRATCH/bookkeeping" origin/main
     # …edit, commit…
     if ! git -C "$SCRATCH/bookkeeping" push origin HEAD:refs/heads/bookkeeping/<slug>; then
       echo "bookkeeping NOT pushed — worktree kept at $SCRATCH/bookkeeping"; exit 1
     fi
     gh pr create --repo <owner/repo> --base main --head bookkeeping/<slug> \
       --title "spec(<feature>): <what>" \
       --body-file <file carrying a "## Review scope" section: the one bookkeeping outcome> \
       || { echo "pushed, but no PR — worktree kept at $SCRATCH/bookkeeping"; exit 1; }
     git -C <repo> worktree remove "$SCRATCH/bookkeeping"
     ```
     Fetch first: this route runs *after* a merge, so a stale `origin/main` would branch
     from an older spec and reopen what the merge just closed. `gh pr create` reads the
     repo from *its own* cwd, not from `git -C <repo>`, so `--repo` and `--base` are
     spelled out — the rest of the block never changes the observer's directory, and an
     unscoped create would target whatever repo it happens to be standing in. The push
     and the create fail separately: a branch pushed with no PR is not done, so the
     worktree stays for that case too.
     The human merges it when the repo's required checks are green, like any PR.
   The worktree is removed only after the push landed; on a conflict or a dead
   network it stays, with the commit in it, and nothing is torn down.
   The pilot's observer once switched the checkout a triage planner was working in;
   staged edits rode along.

## verify

**In:** a milestone PR with the mapping line `Spec: … · Milestone: M<N>`, CI green,
and the **newest section** of its `kbabysit` report carrying `**Verdict:** ✅ merge-ready`.
Any other verdict line — ⚠️ or ❌ — means the loop is not done, and this seat's whole move
is to quote that line and its `**Why the loop stopped:**` line to the human verbatim. A
DISCUSS the human has since decided is closed by the executor's `/kbabysit <n>` re-entry,
which appends a section with the new verdict; **a verdict never changes in chat.**
Measured 2026-09-14: an observer told the human PR #70 was merge-ready while the report's
newest section read `⚠️ needs human decision`, the CodeQL check was red and two of the
three open items were undecided. The human caught it. That is the trust this seat exists
to protect, and the word "merge-ready" is one it repeats from the report, never coins.

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
   means in practice. Record the command and output in a PR comment. **Order:** step 3
   decides the bookkeeping commit and step 4 explains why it has to precede this one, so
   the sequence you actually run is 2 → 3 → 1 → 4. The comparison is only worth anything
   at the head that gets merged, and step 3's commit is what makes that head final.
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
4. **Report:** the report's newest `**Verdict:**` and `**Why the loop stopped:**` lines,
   quoted verbatim, then the re-run evidence and his answers — or blocked, with the
   reason. He merges. **Merge-ready names the head it is true of**, and step 3's
   bookkeeping commit moves the head — so the `In:` condition's green CI and a step 1
   re-run taken before it both describe a head that is no longer the one being merged.
   Required statuses are evaluated per head and re-run on the new one: wait for them.
   Do not reason about whether the commit could have changed the re-run's result — make
   the bookkeeping commit *first* and run step 1 once, at the head you will report. One
   run, no judgement call, and the evidence matches the head by construction.

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

- **Never upgrade a verdict.** The babysit report's newest `**Verdict:**` line is the
  loop's conclusion; relay it verbatim. If it is not ✅, the PR is not merge-ready, whatever
  else looks done. The only thing that changes it is a `/kbabysit <n>` re-entry appending
  a new section.

- Never merge; never decide a product semantic; never edit a brief or an acceptance
  test (planner branches only).
- **Never request a review, never run `kreview`, never relay a disposition.** The two
  review-loop moves are `/kbabysit <n>` to the executor and a question to the human. This
  one cost 20 paid Copilot rounds on 2026-09-13 (#61).
- Never resolve a *For the human* item by reasoning about it — it is a question, not a
  finding.
- Model checked at every start and restart; group passed at every launch; no checkout
  shared with a child. Each of these cost the pilot a round.
