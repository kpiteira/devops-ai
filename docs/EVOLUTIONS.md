# devops-ai — Evolutions Backlog

*A running log of framework evolutions we intend to make. Each entry states the problem before the solution, so entries stay meaningful over time.*

## 1. Human–model contract rewrite (in design)

**Problem:** the kdesign/kplan/kbuild framework prescribes process, which caps frontier models at the human's plan and wastes their planning/verification abilities.
**Direction:** outcome-only intent specs and work briefs, executor agency with an escape valve, anti-deference escalation protocol, comprehension layer (glossary, architecture-as-tests, event-triggered interrogation).
**Status:** v6 piloted end to end on khealth "challenges" (2026-09-01 → 09-11, `docs/designs/v2-contract/PILOT.md`); synthesised in `REVIEW.md`; contract, rules, skills and templates revised to v7 (September 2026). Next: a second pilot on a different product, watching what v7 introduced.

## 2. Conformance & e2e validation integration

**Problem:** the new Fable conformance review covers intent conformance and architectural coherence only; functional e2e validation (as devops-ai does today) must stay, and the two need a clean seam.
**Direction:** define how the intent-level review and the e2e pipeline compose — ordering, shared artifacts (briefs' acceptance criteria as e2e seeds?), what blocks a feature boundary.
**Status:** identified during contract-rewrite review; deliberately kept out of the contract doc's scope.

## 3. Code review process ("babysitting PRs")

**Problem:** PR review currently demands ongoing human attention, and per the new contract, human PR-reading neither catches the failures that matter (cross-PR inconsistency) nor is a good use of energy.
**Direction:** to be designed — likely builds on the Pi validator-agent architecture and the conformance review, with the human involved only at escalation.
**Status:** first concrete step landed 2026-09-12 (devops-ai #34, data in #33): the babysit loop now requires a written `## Review scope` in the PR body, kreview has an OUT OF SCOPE disposition (true but not this PR's → issue), every finding carries a computed provenance (original diff / review-fix commit / unknown; the boundary is the earliest review still in the branch's history, so a rebase resets it at the cost of at most one extra round), and a round whose findings all sit on fix commits is the last one. Six criteria signed by Karl item by item; the pilot data (13- and 11-round loops) is in #33. Also landed 2026-09-12 (#25): the loop runs **forked on an Opus-grade model**, never inline on the invoking session's tier — `skills/kbabysit/SKILL.md` frontmatter carries `context: fork`, `agent: general-purpose`, `background: false` and `model: claude-opus-5` ([skill frontmatter reference](https://code.claude.com/docs/en/skills.md)), for tier economics (polling plus bounded judgement doesn't warrant top-tier tokens) and context hygiene (poll/CI/review output stays out of the invoking session). The fork sees no conversation history, so the skill body carries `$ARGUMENTS` and resolves the PR from the checkout; `kreview` runs inside that subagent, unforked. The human-at-escalation design above is still open.

Second measurement, 2026-09-13 (devops-ai #61, from the `secret-providers` M2 and M3 PRs — #51 is M2, OpenBao; #49 is M3, Azure Key Vault): #49 and #51 drew **13 and 12 Copilot reviews**, and **20 of those 25 were spent outside the loop**. Both PRs stopped correctly *under* `kbabysit` — #49 on budget after 3 rounds, #51 second-order after 2, reports posted — and then, nine hours later, the observer seat ran a hand-rolled loop: it re-requested Copilot itself each round and relayed pre-decided dispositions to the executors (`(1) FIX … (2) IMPLEMENT …`), so no triage, no provenance, no scope judgement and no budget applied to any of the 20. Two content failures compounded it: rounds 6–11 of #49 were five correct patches to five echo sites of **one** root cause (unvalidated `akv://` segments echoed into `az` error text), filed as a class only afterwards, as #60; and only **4 of the 13** Copilot reviews on #49 opened a thread at all — from round 6 (14:27) on, 7 of the last 8 opened none, so 8 of the 9 findings that phase produced were *suppressed comments* living only in review bodies, invisible to a triage that reads threads. Counting them fires the existing second-order stop at round 6: that round's only two findings, `azurekeyvault.py:245` and `:160`, blame at the review's own commit (`70a8f107`) to `23ee88a2` and `63465ed7`, both descendants of the boundary — seven paid rounds after the loop already had the rule to stop. Six mechanisms landed from the signed list: (1) every finding carries `isolated | systemic → <root cause>` before it gets a disposition, and a `systemic` root cause on pinned Surface stops the loop as the human's decision rather than buying the next round; (2) `kselfreview` asks the same question over its own findings and reports a shared mechanism once, not per site; (3) the observer seat has **no re-request verb** and relays no dispositions — `/kbabysit <n>` or a question to the human, nothing else; (4) the first pass should run at Copilot's deeper effort level, which turned out **not** to be request-time — "Review effort level" (`Lite`/`Balanced`) is a repository/organization setting at Settings → Copilot → Code review, with no REST, GraphQL or ruleset parameter, so `kbabysit` records the level per round and names the setting for the human instead of changing it; (5) suppressed comments are parsed out of review bodies, given computed provenance from the review's own `commit_id`, and counted in the second-order stop; (6) **re-entry**: any round after a posted report, from any seat and for any reason, goes through `/kbabysit <n>`, which re-applies the budget and stop rules from that report onward — new commits are a legitimate trigger, but the trigger re-enters the loop, it never bypasses it.

## 4. Roadmap representation & grounding

**Problem:** running multiple teams of agents in parallel creates a heavy context-switch tax; the human needs a way to ground quickly at any moment — where each product stands, what's on deck short-term and long-term.
**Direction:** to be designed — a maintained, always-current roadmap view aggregating feature specs' status across products; possibly generated from the specs themselves so it can't drift from reality.
**Status:** not started.

## 5. CI budget and gate events

**Problem:** the always-run CI job must stay under 2 minutes (hard limit; ideally under 1) — the human's principle, and why it runs unit tests only. The milestone blocking gate is E2E and cannot live there; running it on every push would also be overly expensive.
**Direction:** blocking acceptance tests run as a separate, selectively-triggered workflow — on PR ready-for-review plus a manual re-trigger, required at merge — never in the standing `check` job. Needs per-project infra answers (can this project's stack stand up in a runner at all?).
**Status:** principle agreed 2026-08-30; wiring deferred to its own feature (see roadmap "PR gate wiring").

## 6. kinfra beyond Python containers

**Problem:** kinfra grew up on Python apps in Docker; the quality generation (uv-flavored Makefile, pytest conftest guardrails) is Python-centric with a thinner Node path, and the human is expanding beyond that world.
**Direction:** to be designed — keep the language-agnostic core (worktrees, slots, ports, compose, observability, guards) and make the quality layer pluggable per stack rather than grown by special cases.
**Status:** identified 2026-08-30, not started.
