---
name: kselfreview
description: Adversarial pass over your OWN uncommitted or unpushed work before spending an external review round. Four interrogations drawn from measured failure classes — falsify every check, source every factual claim, run every procedure twice, re-examine closed findings. Finds the defects a diff-reading reviewer structurally cannot.
metadata:
  version: "0.2.0"
---

# kselfreview — interrogate your own work before anyone else does

Run this **before** `kbabysit`, before requesting Copilot, before saying "ready".
External rounds cost money and wall-clock; this costs one pass.

```
/kselfreview                 # working tree + commits not on the base branch
/kselfreview <rev-range>     # e.g. baca4d8..HEAD
```

**This is not a style checklist.** It is four specific interrogations, each derived
from a failure class measured on real work (PR #18, kpiteira/homelab: 9 review
rounds, ~55 findings). Roughly 20 of those 55 were catchable by this pass alone.

The governing observation:

> **A check you author cannot detect your own misunderstanding.** You write the
> check and the thing it checks from one mental model, so the check inherits the
> model's blind spots. Verification is not enough; you have to falsify.

---

## 0. Scope the pass

The invocation decides the scope; the commands follow it, not the other way round.
There are two forms and they do not mix:

```bash
# /kselfreview <rev-range>   — exactly those commits; the working tree is out of scope
git diff --stat <rev-range>
```

```bash
# /kselfreview               — everything not yet on the base branch
BASE=$(git merge-base HEAD origin/main 2>/dev/null || echo main)
git diff --stat "$BASE"                    # committed + staged + unstaged, in one diff against the merge base
git ls-files --others --exclude-standard   # untracked: no diff exists, read each file in full
```

`git diff "$BASE"` with no second revision compares the merge base to the **working
tree**, so a fix left staged or unstaged is in the pass, not just what `HEAD` holds.
Untracked files have no diff to read: open them. An untracked path that is not part of
this work (someone else's WIP in the same checkout) is named in the report as excluded,
never silently skipped — the report must say what the pass did not look at. Gitignored
files are not listed and not reviewed: they cannot reach the PR, so they are not the work.

Enumerate, before reading any code:
- Every **check** introduced: alert rule, assertion, guard, validation, test, exit-code check, health probe, retry condition, monitor.
- Every **factual claim** about a live system: "deployed", "verified", "complete", counts, versions, schedules, addresses, "X is free/unused/handled".
- Every **procedure** a human or script will run: deploy, rollback, migration, cutover, setup.

The three lists are the agenda. Work them in order; they are ranked by how often
they hide something.

---

## 1. Falsify every check — "can this go red?"

*Measured: 7 instances on PR #18. The dominant code-side class.*

For each check on the list, **construct the failure it exists to catch and confirm
it trips.** Not "read it and agree" — produce the input, run it, see it fail.

If you cannot make it go red, it is not a check. Delete it or fix it; never leave
it as a green light that means nothing.

Interrogations that have each caught a real one:

| Ask | Real instance |
|---|---|
| Are both sides of this comparison always present together, or never? | An alert `expected unless threshold` where the generator emits both on adjacent lines or neither — **structurally unfireable** |
| Does this assertion's expected value include things outside its filter? | `count(all rules) == 16` where the count also included three unrelated rule files — **could never pass** |
| Does this pattern also match the malformed input it screens for? | `grep -q '^metric_name '` also matches a line truncated right after the space — the truncation guard passed truncated files |
| What does this aggregate return over an *empty* input? | `count(X) < 4` returns **empty**, not 0, so the "nobody is reporting" alarm went quiet at zero reporters |
| Am I matching an identifier whose real spelling differs? | Polled for `copilot-pull-request-reviewer`; the REST API says `copilot-pull-request-reviewer[bot]`. Reported "no review" forever |
| Would this check pass equally in the broken and healthy case? | `count(A) == count(B)` where both are 6 either way — blind to a label defect in one of them |
| Does a success status actually mean the thing happened? | GitHub returns **`201 Created`** for a review request it silently discards. Check the resulting state, never the status code |

**The last one generalises:** an exit code, HTTP status, or "no output" is evidence
that a call was *accepted*, not that it had an *effect*. Assert on resulting state.

### The ambiguous negative

A check can go red and still be useless if its red means more than one thing.
Ask of every negative result: **how many different causes produce it?** If more
than one, it is not a check, it is an ambiguity — and you will act on the wrong
cause.

One polling script on PR #18 produced four separate wrong conclusions this way,
and each time the empty result was read as "the thing did not happen":

| Cause of the empty result | What it was read as |
|---|---|
| Identifier misspelled (`[bot]` suffix missing) | reviewer had nothing to say |
| Request silently discarded by the API | reviewer is unavailable |
| Work still in progress, not yet submitted | reviewer never came |
| Results past page 1, `--paginate` missing | no new results exist |

The fix in every case is the same: make the check report *which* state it found,
not merely the absence of the one you wanted. Distinguish **absent**, **pending**,
**failed**, and **I could not tell** — and exit differently for each. A poller
that cannot say "still running" will eventually tell you a running thing is dead.

Paging is the quiet one: a filter over a paginated API silently stops seeing new
items once the list outgrows the first page, and reports success the whole time.

And when a check reads **two sources** — a status flag and the artefact the work
produces — the terminal flag can flip before the artefact appears. Re-read the
artefact *after* observing completion, with a grace period, before concluding
"finished and produced nothing". Otherwise the race reports a clean result as
confidently as a real one. (Observed: a rebuilt poller declared
`completed_without_review` eight seconds before the review it was waiting for
was submitted.)

---

## 2. Source every factual claim — "how do I know, and when was that true?"

*Measured: 11 instances, the single largest class. Two-thirds of all findings on
PR #18 were in prose, not code.*

Documentation is state. It goes stale at the moment of writing, and nothing
re-derives it.

For every claim about a live system, require one of:
- the **command that re-derives it**, inline; or
- a **timestamp plus how to verify**; or
- deletion.

Then run the specific interrogations:

- **Does this document contradict itself?** Grep for the same fact stated twice.
  A value repeated in N places drifts. *Instances: `06:00 UTC` in one section and
  `06:00 local` 110 lines away; a round count that read "three", "four" and "five"
  in one PR.* **Fix by deleting the duplicate, not by correcting it** — one
  authoritative location, everything else refers to it.
- **Does any summary claim a state the body disproves?** Summary tables are state
  too. *Instance: a findings table marking an item "fixed" while a warning box in
  the same file explained it was not fixable.*
- **Does a claim of completion match the thing it claims about?** *Instance: four
  documents said "DONE"/"COMPLETE" while production ran pre-review code, because
  fixes landed after the deploy. Check the artifact, not the commit log.*
- **Does a describing comment still describe what is below it?** *Instance: an
  alert's operator description named the wrong fallback signal after a rule added
  two commits earlier changed the answer.*
- **Is anything called "free", "unused", "empty", "handled" or "safe to remove"?**
  Grep for who still references it before believing it. *Instance: IP addresses
  documented as free while DNS resolved names to them and a credential's CIDR
  binding still permitted them.*
- **Do quantities in prose match the code?** *Instances: "all VMs" for a list of
  one; "four touches" for a five-host procedure.*

---

## 3. Run every procedure twice — "what happens on the second run?"

*Measured: 4 instances, and all four came from this single question.*

Walk each procedure on paper for:

1. **A second run**, on a system where the first already succeeded.
2. **A resumed run**, after failure at each step in turn.
3. **The rollback**, on a system where the forward path partly ran.

Specific traps, each a real instance:

- **Does a backup step overwrite the good copy with the damaged one?**
  `cp live.conf live.conf.bak` on the second run snapshots the *already-modified*
  file under a name claiming it is pristine.
- **Does a step consume its own source?** `mv a b` fails on the second run — and
  an unguarded failure mid-procedure leaves a half-state.
- **Where does the input come from?** A procedure that installs from `/tmp`
  without saying how `/tmp` is populated will reinstall **whatever was staged
  last time** — and report success. Stage explicitly and assert on *content*
  (`grep -q <new-symbol> || exit 1`), never on the file existing.
- **Does the rollback destroy before it validates?** Establish the restore source
  is genuine *first*; abort untouched if not. A rollback that deletes the new
  thing and then fails to restore the old one leaves you worse off than either
  state it was choosing between.
- **Does the rollback reference something the forward path never created?**
  Trace every restore source to the exact line that produces it.

---

## 4. Re-examine closed findings — "did this round change an old verdict?"

*Measured: 4 instances of a fix introducing a defect; one of a dismissal expiring.*

After each round of changes, revisit what was previously decided:

- **Did a fix introduce a defect?** *Instance: a counter moved above a gate made an
  all-disabled config look healthy.* Treat your own fixes as unreviewed code —
  they are the least-reviewed code in the change.
- **Did a change invalidate an earlier dismissal?** *Instance: `disable 0` parsed
  as "disabled" was correctly rated low because it failed loudly. Three rounds
  later a new critical alert turned the same unchanged line into a false page.*
  **A finding's severity is a function of the whole system, not of its line.**
- **Did a new label, name, or key collide with a reserved one?** *Instance: a
  metric label named `job` — reserved by Prometheus — was silently renamed on
  ingest, so the alert paged with the wrong value.* Check the platform's reserved
  namespace before inventing a name.
- **Does a new fix claim more than it delivers?** *Instance: adding a job label
  made two series distinct, which fixed a crash — but the underlying value was
  still derived from a source with no job identity, so one job still masked the
  other. The label bought separation in name only.*

---

## The shape check — isolated or systemic?

*Not a fifth interrogation: this runs over the **findings** the four produced, after
they are all in, and it is the last thing you do before writing the report.*

Ask of every finding: **is this an isolated incident, or one site of a mechanism that
has others?** Label each `isolated` or `systemic → <root cause>` — a `systemic` label
with no root cause named is an `isolated` one wearing a label.

Then the shape check over the list as a whole: **if two findings share a mechanism, the
report names the mechanism once, not the sites.** One finding, one root cause, the sites
listed underneath it as evidence that the class is real. A list of five siblings reads
as five small things to patch; the same list collapsed to its mechanism reads as the one
thing to change, which is what it is.

This is the pass's cheapest yield and its easiest miss, because the four interrogations
above work finding by finding and a finding has no view of its siblings. Measured: PR #49
went to review with a class of defect — unvalidated `akv://` segments echoed into `az`
error text — that had five sites. Nothing named the class; Copilot found the sites one at
a time across rounds 6–11, each patch correct and none of them the fix, and the class was
filed afterwards as #60. A shape check before the first review round had one row to write.

The same rule as `kreview`'s decides what a `systemic` finding becomes: if the root cause
sits on **pinned Surface** (something the brief or the spec pins), it is not yours to
close — it goes to the human, named, with its sites as evidence. Otherwise: the class fix
in one commit, or one issue for the class. Never a patch per site.

---

## Output

A short report. Findings ranked, each with file:line, its `isolated | systemic → <root
cause>` label, the mechanism, a concrete
failure scenario, and — stated separately — whether you **verified it by running
something** or reasoned by inspection. Do not blur those two.

Then, explicitly: **what you checked and found clean.** A pass that reports only
findings gives no information about coverage.

"I found nothing" is a valid and useful result. Inventing marginal findings to
look thorough is a failure of the pass.

---

## Guardrails

- **Read-only on infrastructure.** Never SSH to a host whose auth needs a physical
  touch just to review. If a claim can only be settled live, say so and let the
  human decide whether it is worth the touch.
- **Falsify by simulation, not in production.** Extract the logic into a scratch
  script and feed it the failing input.
- **Don't re-litigate the design.** This pass hunts defects in what was built, not
  arguments about what to build.
- The four sections are ordered by yield. If you only have time for one, do §1 on
  checks and §2 on any claim containing the word "complete", "done" or "verified".
- **The shape check is never the thing you skip.** It runs over findings you already
  have, so it costs one pass over a list you just wrote — and it is the only part of this
  skill that can turn five findings into one.
