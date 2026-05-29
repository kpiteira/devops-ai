# Modeler 1 — Findings (recovered from subagent inline reply; side-file write was blocked)

### Finding: MemoryService is a god-class

- **Observation:** Single class funnels pipeline orchestration, all result dataclasses, dialogue helpers, migration, ingest, audit, eval/cost factories, runtime factories, busy-queue/lock state
- **Evidence:** `src/agent_memory/services.py:202` (`class MemoryService`); 2286 lines. Imported as single entry point from both `api.py` and `scheduler.py`
- **Why it might matter:** No internal seams; every new capability becomes another method here; testing requires holding the whole system in memory
- **Suggested layer for deeper investigation:** L2

### Finding: MemoryScheduler is an integration hub, not just a scheduler

- **Observation:** Scheduler module carries approval handling, content-tap gating, escalation routing, dialogue task lifecycle far beyond scheduling
- **Evidence:** `src/agent_memory/scheduler.py:36` (`handle_approval`), `:77` (`handle_skill_approval`), `:144` (`_make_reply_handler`). 1769 lines
- **Why it might matter:** Scheduling concerns mixed with action-execution glue; safety routing lives in a helper closure
- **Suggested layer for deeper investigation:** L2

### Finding: AgentHome is an implicit schema masquerading as a path resolver

- **Observation:** Every consumer reaches `home.*_dir` rather than going through a memory-store interface; no explicit storage contract
- **Evidence:** `src/agent_memory/agent_home.py` (1307 lines); consumed at `api.py:189, 199, 208`
- **Why it might matter:** The "memory store" capability is implicit; no enforced shape; invariants live in path conventions instead of a contract
- **Suggested layer for deeper investigation:** L3

### Finding: Lazy in-function imports hide the dependency graph

- **Observation:** Runtime/eval/cost factories imported inside methods rather than at module top, signalling prior import-cycle pain
- **Evidence:** `services.py:225, 230, 244`
- **Why it might matter:** Conceptual orchestrator→phase→runtime graph is held together at runtime, not in module imports — invisible to static tooling
- **Suggested layer for deeper investigation:** L2/L3

### Finding: README claim "Generate / Prepare have no LLM" is partly false

- **Observation:** README pipeline table marks Generate/Prepare as non-LLM; in reality Generate makes an LLM call for cross-project relevance ranking during MEMORY.md composition
- **Evidence:** README pipeline table vs `retrieval/generator.py:32` (`_ELSEWHERE_RELEVANCE_SYSTEM`)
- **Why it might matter:** Doc-vs-code drift on a load-bearing claim; readers building a mental model from the README will be wrong about the hottest path
- **Suggested layer for deeper investigation:** L2

### Finding: Guardian is wired in via a scheduler closure

- **Observation:** 12-module `guardian/` package composed with the dialogue agent only inside a helper closure in the scheduler — safety glued onto another module's internal helper
- **Evidence:** `scheduler.py:169` (`_gated_route` inside `_make_reply_handler`)
- **Why it might matter:** Safety-critical concern wired in a way that's hard to discover and hard to enforce; no explicit safety boundary
- **Suggested layer for deeper investigation:** L2

### Finding: `/squads` and `/skills` are first-class HTTP surfaces undocumented in the README

- **Observation:** Two substantial subsystems mounted at top-level HTTP routes, with backing packages, but absent from the public README narrative
- **Evidence:** `api.py:187-213` mounts both
- **Why it might matter:** Public surface wider than the public story — either under-documented or speculative; security and onboarding hazard
- **Suggested layer for deeper investigation:** L2
