# Handoff — Milestone 4: Agent-Deck Integration + kworktree Skill

## Task 4.1 Complete: Agent-Deck Module

**Approach:** Standalone module using `functools.lru_cache` for `is_available()` caching and a private `_run_command()` helper for all subprocess calls. All public functions check availability first and return early if not available.

**Key patterns:**
- `is_available()` uses `lru_cache(maxsize=1)` — tests must call `is_available.cache_clear()` in `setup_method`
- `_run_command()` handles all subprocess calls: `capture_output=True, text=True`, logs warning on failure stderr, never raises
- `AgentDeckError` exists but not used yet — available for CLI layer to catch if needed

## Task 4.2 Complete: CLI --session Flag Integration

**Approach:** Added `_setup_session()` helper in impl.py that encapsulates the add→start→send sequence. Both no-sandbox and sandbox paths call it when `session=True`. done.py uses `_session_title_from_worktree()` to derive the session title from the branch name.

**Key patterns:**
- `import devops_ai.agent_deck as agent_deck` (module-level import) — tests mock it as `devops_ai.cli.impl.agent_deck`
- `_setup_session()` returns a status message string, appended to the main output
- `main.py` passes `session=` kwarg — `typer.Option(False, "--session", help="...")`
- done.py derives title from branch: `impl/feat-M1` → `feat/M1`, `spec/feat` → `spec/feat`

## Task 4.3 Complete: kworktree Skill

**Approach:** Single markdown skill at `skills/kworktree/SKILL.md` (167 lines). Covers context detection, all commands, workflows, sandbox-aware coding, observability endpoints, error handling, and project config reference.

**Key decisions:**
- Compressed workflow section to single-line format to stay under 200 lines
- Referenced `infra.toml` conceptually rather than including full example (saves ~12 lines)
- Observability endpoints hardcoded (they're fixed at 4xxxx range)

## Task 4.4 Complete: M4 E2E Verification

**Bugs found and fixed during real E2E testing:**

1. **add_session CLI syntax** — Code used `agent-deck add <title> --group <group> --path <path>` but real CLI expects `agent-deck add <path> -t <title> -g <group>`. Fixed in `agent_deck.py`.

2. **done session title mismatch** — `done_command` passed `wt.feature` (hyphenated: `feat-M1`) but sessions are created with slash format (`feat/M1`). Fixed by adding `_session_title_from_worktree()` that derives title from branch name using regex.

**Validation results:**
- Unit tests: 172/172 PASSED (includes 6 new tests for bug fixes)
- E2E tests: 7/7 PASSED (real agent-deck session lifecycle + skill structure)
- Ruff + Mypy: All clean
- Regression: All pre-existing tests (M1-M3) pass
