# Architecture Findings — agent-memory

> Findings noticed during audit. Each entry has draft severity; formal severity assigned at L4. Append-only across audit layers.

| ID | Layer | Title | Evidence | Severity (draft) | Status | Notes |
|---|---|---|---|---|---|---|
| F001 | L1 | `services.py` is a 2,286-line orchestration god-module | `src/agent_memory/services.py:202` (`class MemoryService`); 2,286 lines; single entry point from `api.py` and `scheduler.py` | high | open | convergent (M1+M2+M3); suggested-layer: L2 |
| F002 | L1 | `scheduler.py` carries approval / channel / safety routing far beyond scheduling | `src/agent_memory/scheduler.py:36` (`handle_approval`), `:77` (`handle_skill_approval`), `:144` (`_make_reply_handler`); 1,769 lines | high | open | convergent (M1+M2+M3); suggested-layer: L2 |
| F003 | L1 | `agent_home.py` mixes path resolution with large embedded markdown identity / seed templates | `src/agent_memory/agent_home.py` (1,307 lines); consumed at `api.py:189, 199, 208` | high | open | convergent (M1+M2+M3); suggested-layer: L3 |
| F004 | L1 | Guardian (safety subsystem) wired in via a closure inside the scheduler | `scheduler.py:169` (`_gated_route` inside `_make_reply_handler`); 12-module `guardian/` package composed only here | high | open | single-source (M1); suggested-layer: L2 |
| F005 | L1 | README onboarding points at deprecated config path while code uses `~/.kagents/<agent-id>/` | README config section vs `agent_home.py`; active `migrate` command exists | medium | open | convergent (M2+M3); suggested-layer: L2 |
| F006 | L1 | Lazy in-function imports of runtime / eval / cost factories hide the dependency graph | `services.py:225, 230, 244` | medium | open | single-source (M1); suggested-layer: L2/L3 |
| F007 | L1 | `cli.py` is 1,238 lines despite README framing it as a "thin HTTP client" | `src/agent_memory/cli.py` (1,238 lines) | medium | open | single-source (M2); suggested-layer: L2 |
| F008 | L1 | `/squads` and `/skills` are first-class HTTP surfaces absent from public README narrative | `api.py:187-213` | medium | open | single-source (M1); suggested-layer: L2 |
| F009 | L1 | Package layout mirrors pipeline phases not capabilities — conceptual components span multiple packages | `MemoryPipeline` spans 6 dirs; `BriefingComposer` spans `retrieval/`+`preparation/` | medium | open | single-source (M3); suggested-layer: L2 |
| F010 | L1 | README "Generate / Prepare have no LLM" is partly false — Generate makes an LLM call | README pipeline table vs `retrieval/generator.py:32` (`_ELSEWHERE_RELEVANCE_SYSTEM`) | medium | open | single-source (M1); suggested-layer: L2 |
| F011 | L1 | `runtime/profiles/{claude,copilot}.py` and `runtime/sdk/{claude,copilot}.py` are twin subtrees with unclear separation | `src/agent_memory/runtime/profiles/`, `src/agent_memory/runtime/sdk/` | low | open | single-source (M2); suggested-layer: L2 |
