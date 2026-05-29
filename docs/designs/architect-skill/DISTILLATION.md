# karchitect: what to keep when we redesign it

**Status:** input for a fresh karchitect design · **old version saved at:** commit `1fdc2c9`

karchitect was a set of ideas for tooling that helps stop a codebase's architecture from rotting —
auditing an existing system, keeping an honest map of it, and reviewing new work against it. We
designed it in May 2026 but **never actually used it.** You now want to redesign it from scratch:
partly because we're on a much stronger model (Opus 4.8), partly because we've changed how we think
skills should be written (give the model the goal and the checks, not a rigid script).

This document is the input for that redesign. It answers three things:

- **What the old version got right** — keep it.
- **What it got wrong** — drop it.
- **What we still have to decide** — the open questions for the new design.

The old version is fully saved in git (commit `1fdc2c9` — this folder plus `skills/karchitect-audit/`),
so starting over loses nothing.

---

## The shape: three jobs, and which to build first

*(decided with Karl, 2026-06-03)*

karchitect isn't one thing. It's three different jobs, and lumping them into one skill is part of
what made the old design confusing:

1. **Get the map** — *audit.* Describe a system's architecture as it actually is. Factual, no
   opinions. This is what most of your projects are missing right now, and it's the part that
   bothers you.
2. **Get clean** — *refactor.* Find the real architectural problems and fix them. Opinionated.
   Builds on the audit. (agent-memory examples: reads and writes scattered all over instead of
   going through one gateway — so there's nowhere to add prompt-injection checks on reads or
   appropriateness checks on writes; and the coding-agent dependency hardcoded as Claude Code in
   some places but abstracted in others.)
3. **Stay clean** — keep the architecture from rotting *while* designing, planning, and building,
   and keep its description current as the code changes.

**The audit is the keystone — the other two mostly sit on top of it or are already underway:**

- The audit produces *two things at once*: the factual map (job 1) **and** a list of problems (the
  input to job 2). The old run already found agent-memory's — the 2,286-line god-module, the
  scheduler doing routing it shouldn't. So **a good audit hands you the refactor targets for free.**
- **"Get clean" needs almost no new tooling.** Audit findings → a `/kdesign` refactor brief →
  `/kplan` → `/kbuild`. The execution is the pipeline we already have and just improved. (Maybe a
  thin bridge from "findings list" to "refactor brief" — probably not a whole skill of its own.)
- **"Stay clean" is already half-built.** Updating the architecture doc from coding reality is the
  *Architecture Reconciliation* step we added to kbuild last week. The other half — checking we're
  not rotting as we go — is the cross-file mechanical checks (duplicate code, layering violations)
  we want to move into the normal quality gates so they run on every change.

**Decision: build the audit first, and try it on agent-memory.** One build serves all three jobs —
it gives you the factual architecture document that *every* undocumented project needs (not just
agent-memory); on agent-memory the audit's findings *are* the refactor plan you've wanted; and
"stay clean" keeps running in the build loop meanwhile. Refactor execution and the "check" half of
stay-clean follow naturally — neither needs to come first.

---

## What it got right (keep)

We actually ran the one piece that got built — the "System Context" audit — against agent-memory,
twice. It worked. From that run:

- **Separate "what the system is" from "what's wrong with it."** The old audit built a plain
  description of the system first, and kept the list of problems in a *separate* file. That
  separation is the whole point — the earlier May audit failed precisely because it jumped straight
  to a pile of problems with no clear picture of the system. Keep this.
- **The problem list was good and specific.** It found the real messes — a 2,286-line god-module
  (`services.py`), a scheduler doing approval and routing work it shouldn't — each pinned to an
  exact `file:line`. It described *problems*, not *facts* ("X has accreted unrelated
  responsibilities," not "X is 2,286 lines"). Keep this format.
- **Multiple independent readers gave a confidence signal.** The audit ran three agents that each
  read the codebase *without seeing each other's work*, then merged their findings. Each problem got
  tagged with how many of them caught it independently ("all three" vs "only one"). That "three
  people independently noticed this" signal is real confidence you cannot get from a single agent,
  no matter how good. Keep this — it's the most valuable thing the old design produced.
- **The quality bar was right.** A reader should understand the system in 5 minutes; the high-level
  diagram should have no implementation detail in it; the agents should be allowed to disagree
  (forced agreement is a warning sign). Keep these as the bar the new version must clear.

So the restart is **not** "the old version was wrong." It understood *what good architecture
understanding looks like.* It just made producing it far more complicated than it needs to be.

## What to drop

- **The rigid five-stage program.** The old design was built as five fixed layers (L1→L5), each a
  separate phase that had to finish and pass before the next began. The *idea* of zooming from
  high-level to detailed is good and standard (it's the C4 model). The rigid staged machinery around
  it is the over-engineering.
- **The step-by-step orchestration written out in prose.** The old skill spelled out, by hand,
  exactly how to spawn the three reader-agents, what to do if one produced bad output, and the exact
  order of the merge. The model can run that fan-out itself now — the skill should say *what we want
  and how we'll check it*, not script the mechanics.
- **The assumption that this must be four separate skills.** (Audit, map, design-review, and
  adversarial-review.) Now re-shaped into three *jobs* with the audit first — see "The shape" above.

## The one distinction the new design has to keep straight

The old skill's multi-agent machinery was doing **two different jobs that look the same on the page:**

1. **Checking the work** — three agents reading independently so we can trust a finding more when
   they all catch it. This is verification. **Keep it**, and let the model orchestrate it natively
   instead of us scripting it.
2. **Scripting the steps** — the exact "do this, then this, reject and retry if that" protocol. This
   is just telling a capable model how to walk. **Drop it.**

The old version fused these into one 140-line procedure. The new version should keep #1 as a clean,
simple mechanism and shed #2.

## What's still open

The big "how many skills" question is settled above. These remain for the audit design — the first
build — and several are genuinely yours to weigh:

1. **How simple can the audit get** before its quality drops? This is the first thing to work out,
   and it's testable: we have the old run's output saved as a baseline to beat.
2. **Is the map a maintained document or re-derived on demand?** With Opus 4.8's large context
   window, an agent can read much of a codebase when needed. So does the audit write an
   `ARCHITECTURE.md` that then has to be kept current, or do we just re-run the audit when we want a
   fresh map? (This shapes "stay clean" too.)
3. **Where do the mechanical checks live?** Cross-file duplication and layering violations are the
   one piece a better model can't replace. I lean toward moving them into the normal quality gates
   so they run on every change, rather than only inside an audit. Worth confirming.
4. **Did kdesign already absorb the "design-time review" piece?** We just added jobs-to-be-done, an
   implementation-readiness checklist, and a command-query check to `/kdesign`. Before building any
   separate "review the design" step, check whether kdesign already covers it.

## How to restart

Run a fresh design conversation (`/kdesign`-style) with **this document as the starting context**,
and the old version available to look at (saved at `1fdc2c9`). Put the result in a new folder
(`docs/designs/karchitect-v2/`) so the old design stays untouched as the record, and the new one is
a clean start rather than an edit of the old.

---

### Background the new design can lean on (unchanged by the model upgrade)

- **The problem it exists for:** agent-memory rotted into 24K lines of tangled code — six parallel
  writer classes, 420+ places writing state directly instead of through the one gateway, message
  logic mixed into transport code. karchitect is meant to catch and prevent that.
- **The established practices it's built on** (all still valid): the **C4 model** (describe a system
  at four zoom levels), **ADRs** (one short file per decision, recording *why*), **arc42** (a
  checklist of what to cover), the **Google design-doc shape**, and Will Larson's **"read five real
  flows, then summarize"** for understanding an unfamiliar codebase.
- **The core lesson:** go evidence → a clear picture of the system → recommendations. Never skip the
  middle step. That middle step (synthesis) is what the May audit was missing.
</content>
