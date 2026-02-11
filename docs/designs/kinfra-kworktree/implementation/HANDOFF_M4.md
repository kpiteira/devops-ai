# Handoff — Milestone 4: Agent-Deck Integration + kworktree Skill

## Task 4.1 Complete: Agent-Deck Module

**Approach:** Standalone module using `functools.lru_cache` for `is_available()` caching and a private `_run_command()` helper for all subprocess calls. All public functions check availability first and return early if not available.

**Key patterns:**
- `is_available()` uses `lru_cache(maxsize=1)` — tests must call `is_available.cache_clear()` in `setup_method`
- `_run_command()` handles all subprocess calls: `capture_output=True, text=True`, logs warning on failure stderr, never raises
- `AgentDeckError` exists but not used yet — available for CLI layer to catch if needed

**Next Task Notes (4.2):**
- Import from `devops_ai.agent_deck`: `is_available`, `add_session`, `remove_session`, `start_session`, `send_to_session`
- `impl_command()` currently returns `(exit_code, msg)` — add `session` parameter, call agent-deck after sandbox setup
- `done_command()` — call `remove_session()` before sandbox stop (best-effort)
