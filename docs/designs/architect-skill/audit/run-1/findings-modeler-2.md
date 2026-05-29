# Modeler 2 — Findings (recovered from subagent inline reply; side-file write was blocked)

### Finding: `services.py` is the de-facto orchestrator, not a thin service layer

- **Observation:** Imports from nearly every subpackage; 2,286 lines
- **Evidence:** `src/agent_memory/services.py`
- **Why it might matter:** What the README describes as "service layer" is actually a top-level orchestrator
- **Suggested layer for deeper investigation:** L2

### Finding: `scheduler.py` contains approval handlers, channel reload, quiet hours — far beyond scheduling

- **Observation:** 1,769 lines mixing scheduling with control-plane and approval logic
- **Evidence:** `src/agent_memory/scheduler.py`
- **Why it might matter:** Scheduler is the wrong owner for approval and channel-reload concerns
- **Suggested layer for deeper investigation:** L2

### Finding: `agent_home.py` mixes path resolution with large embedded markdown identity/seed templates

- **Observation:** 1,307 lines; path resolution is a small fraction of the file's content
- **Evidence:** `src/agent_memory/agent_home.py`
- **Why it might matter:** Templates versioned with code rather than as data; conflates two concerns
- **Suggested layer for deeper investigation:** L3

### Finding: `cli.py` is 1,238 lines despite the README describing it as a "thin HTTP client"

- **Observation:** Significant logic hidden behind a "thin client" framing
- **Evidence:** `cli.py` (1,238 lines)
- **Why it might matter:** Doc/code drift; CLI may have business logic that should live in the container
- **Suggested layer for deeper investigation:** L2

### Finding: `runtime/profiles/{claude,copilot}.py` and `runtime/sdk/{claude,copilot}.py` are twin subtrees with unclear separation

- **Observation:** Two parallel package trees with identical filenames; separation of concerns between "profile" and "sdk" not obvious
- **Evidence:** `src/agent_memory/runtime/profiles/`, `src/agent_memory/runtime/sdk/`
- **Why it might matter:** Adds cognitive load; risk of duplicate logic across the twins
- **Suggested layer for deeper investigation:** L2

### Finding: README points to deprecated config path

- **Observation:** README states config lives at `~/.agent-memory/config.yaml`, but the rest of README and `agent_home.py` use `~/.kagents/<agent-id>/`; an active `migrate` command exists
- **Evidence:** README config section vs `agent_home.py`
- **Why it might matter:** New users follow the wrong path; doc drift on a load-bearing setup step
- **Suggested layer for deeper investigation:** L2
