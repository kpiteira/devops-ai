# Modeler 3 — Findings (recovered from subagent inline reply; side-file write was blocked)

### Finding: `services.py` is a 2,286-line orchestration god-module

- **Observation:** Touches nearly every subpackage
- **Evidence:** `src/agent_memory/services.py` (2,286 lines)
- **Why it might matter:** Single point that knows everything; no internal seams
- **Suggested layer for deeper investigation:** L2

### Finding: `agent_home.py` mixes path resolution with large embedded markdown seed content

- **Observation:** 1,307 lines combining a path resolver with extensive identity/charter prose
- **Evidence:** `src/agent_memory/agent_home.py`
- **Why it might matter:** Identity content versioned in Python source, not as data — prompt edits become code commits
- **Suggested layer for deeper investigation:** L3

### Finding: `scheduler.py` carries action-execution domain logic (`handle_approval`) that belongs in a skill/action layer

- **Observation:** Approval handling is scheduling-adjacent at best; the scheduler is owning a domain it shouldn't
- **Evidence:** `scheduler.py` `handle_approval` and related functions
- **Why it might matter:** Action-execution flow is split across scheduler and skills — boundary in the wrong place
- **Suggested layer for deeper investigation:** L2

### Finding: Documented dual home roots create drift risk

- **Observation:** `~/.kagents/` vs `~/.agent-memory/config.yaml` both referenced; an active `migrate` command exists
- **Evidence:** README + `agent_home.py`
- **Why it might matter:** Public-doc onboarding step pointed at deprecated location; users will hit migration unexpectedly
- **Suggested layer for deeper investigation:** L2

### Finding: Conceptual components don't align with top-level packages

- **Observation:** `MemoryPipeline` spans 6 dirs; `WorkingMemoryComposer` spans `retrieval/`+`preparation/`; package layout mirrors pipeline phases rather than capabilities
- **Evidence:** `src/agent_memory/` package layout vs the conceptual model
- **Why it might matter:** Package boundaries advertise modularity that the call graph doesn't honour
- **Suggested layer for deeper investigation:** L2
