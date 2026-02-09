---
design: docs/designs/kinfra-kworktree/DESIGN.md
architecture: docs/designs/kinfra-kworktree/ARCHITECTURE.md
---

# Milestone 4: Agent-Deck Integration + kworktree Skill

**Goal:** A developer can run `kinfra impl feature/M1 --session` to get a worktree, sandbox, AND an agent-deck session with Claude running and the milestone command auto-sent. The `kworktree` skill provides the conversational interface for AI coding tools.

**Branch:** `impl/kinfra-kworktree-M4`
**Builds on:** Milestone 2

---

## Task 4.1: Agent-Deck module

**File(s):**
- `src/devops_ai/agent_deck.py` (create)
- `tests/unit/test_agent_deck.py` (create)

**Type:** CODING
**Task Categories:** External, Configuration

**Description:**
Implement the agent-deck integration module that checks for availability, manages sessions (add, remove, start, send), and handles graceful degradation when agent-deck is not installed. All operations are best-effort — failures are warnings, not errors.

**Implementation Notes:**
- `is_available()` → `bool`:
  - Check `shutil.which("agent-deck")` — returns True if found on PATH
  - Cache result for the lifetime of the process (check once)
- `add_session(title, group, path)`:
  - Run: `agent-deck add <title> --group <group> --path <path>`
  - Session naming: spec → `spec/<feature>` in group `dev`, impl → `<feature>/<milestone>` in group `dev`
- `remove_session(title)`:
  - Run: `agent-deck remove <title>`
  - Ignore errors (session may already be removed)
- `start_session(title)`:
  - Run: `agent-deck session start <title>`
  - This launches Claude in a tmux pane
- `send_to_session(title, message, delay)`:
  - Wait `delay` seconds (default 3s) before sending — agent-deck needs time to start (GAP-20)
  - Run: `agent-deck session send <title> "<message>"`
  - The message is typically `/kmilestone <feature>/<milestone>`
- All subprocess calls:
  - Use `subprocess.run()` with `capture_output=True`, `text=True`
  - On failure: log warning with stderr, do NOT raise
  - Check `is_available()` before every operation — early return if not available
- `AgentDeckError` exception class for internal use (caught at CLI layer, turned into warnings)

**Tests:**
- Unit: `tests/unit/test_agent_deck.py`
  - `test_is_available_found`: mock `shutil.which` returns path → True
  - `test_is_available_not_found`: mock `shutil.which` returns None → False
  - `test_add_session_command`: verify correct command construction
  - `test_add_session_spec_naming`: spec feature → `spec/<feature>` in group `dev`
  - `test_add_session_impl_naming`: impl feature/milestone → `<feature>/<milestone>` in group `dev`
  - `test_remove_session_ignores_errors`: subprocess fails → no exception
  - `test_start_session_command`: correct command
  - `test_send_with_delay`: verify delay parameter passed correctly
  - `test_all_ops_skip_when_unavailable`: every function returns early when not available
  - `test_subprocess_failure_warns`: stderr captured and logged

**Acceptance Criteria:**
- [ ] `is_available()` correctly detects agent-deck on PATH
- [ ] Session add/remove/start/send construct correct commands
- [ ] Naming convention: spec → `spec/<feature>`, impl → `<feature>/<milestone>`
- [ ] All failures produce warnings, not errors
- [ ] All operations skip cleanly when agent-deck not installed

---

## Task 4.2: CLI --session flag integration

**File(s):**
- `src/devops_ai/cli/impl.py` (modify — add `--session` flag)
- `src/devops_ai/cli/done.py` (modify — add session cleanup)
- `tests/unit/test_cli_impl_session.py` (create)

**Type:** CODING
**Task Categories:** API Endpoint (CLI), Cross-Component

**Description:**
Add the `--session` flag to `kinfra impl` that triggers agent-deck session creation after sandbox setup. Extend `kinfra done` to clean up agent-deck sessions. Both degrade gracefully when agent-deck is unavailable.

**Implementation Notes:**
- `kinfra impl <feature/milestone> --session`:
  - After sandbox is running (or worktree created if no sandbox):
    1. Check `agent_deck.is_available()`
    2. If not available: "agent-deck not found, skipping session management"
    3. If available:
       a. `agent_deck.add_session(title=f"{feature}/{milestone}", group="dev", path=worktree_path)`
       b. `agent_deck.start_session(title)`
       c. `agent_deck.send_to_session(title, f"/kmilestone {feature}/{milestone}", delay=3)`
       d. Report: "agent-deck session started: {feature}/{milestone}"
  - `--session` without agent-deck: warning only, not an error
  - `--session` with spec worktrees: also works (session without sandbox is valid)
- `kinfra done <name>` (extended):
  - Before stopping sandbox:
    1. Check if agent-deck is available
    2. If so: `agent_deck.remove_session(title)` — best effort
    3. If session is actively running (GAP-21): warn "Session is still running. Use --force to proceed."
  - Note: checking if session is running requires `agent-deck session status <title>` — if agent-deck doesn't support this, skip the check and just remove
- The `--session` flag is a `typer.Option(False, help="Create an agent-deck session with Claude")`

**Tests:**
- Unit: `tests/unit/test_cli_impl_session.py`
  - `test_session_flag_with_agent_deck`: all 3 agent-deck calls made in order
  - `test_session_flag_without_agent_deck`: warning printed, impl succeeds
  - `test_session_send_delay`: delay parameter passed to send
  - `test_session_send_correct_command`: `/kmilestone <feature>/<milestone>` sent
  - `test_done_removes_session`: agent_deck.remove called during done
  - `test_done_no_agent_deck_skips`: done succeeds without agent-deck
  - `test_session_with_spec`: works for spec worktrees too

**Acceptance Criteria:**
- [ ] `--session` creates agent-deck session after sandbox setup
- [ ] Session receives `/kmilestone` command with correct feature/milestone
- [ ] 3-second delay before sending command (agent startup time)
- [ ] `done` cleans up agent-deck session
- [ ] Missing agent-deck produces warning, not error
- [ ] `--session` works with both impl and spec worktrees

---

## Task 4.3: kworktree skill

**File(s):**
- `skills/kworktree/SKILL.md` (create)

**Type:** CODING
**Task Categories:** Configuration

**Description:**
Create the kworktree skill that provides a conversational interface for AI coding tools (Claude Code, etc.) to manage worktrees and sandboxes via kinfra commands. The skill teaches the AI tool how to use kinfra, what the commands do, and when to use them.

**Implementation Notes:**
- The skill is a markdown file that gets loaded into the AI tool's context
- It should cover:
  - **Commands reference**: all kinfra commands with arguments and expected output
  - **Workflows**: common sequences (init → spec → done, init → impl → done)
  - **Context awareness**: how to detect if the user is in a worktree (check branch name pattern, check `git worktree list`)
  - **Sandbox awareness**: how to check sandbox status (`kinfra status`)
  - **Port awareness**: when writing code that references service URLs, use the sandbox port (from `kinfra status`) not the hardcoded base port
  - **Error handling**: what to do when sandbox fails to start, when done fails on dirty worktree
  - **Observability**: how to check traces in Jaeger (link to UI with namespace filter)
- Follow the pattern of ktrdr's existing kworktree skill (studied during design) but generalized for any project
- Keep it concise — the skill will be loaded into context, so every line should earn its place
- Reference `infra.toml` for project-specific details rather than hardcoding project info

**Tests:**
- Manual verification: invoke via Claude Code, verify correct kinfra commands issued
- Structural: skill file exists, contains expected sections

**Acceptance Criteria:**
- [ ] Skill file exists at `skills/kworktree/SKILL.md`
- [ ] Covers all kinfra commands (init, spec, impl, done, worktrees, status, observability)
- [ ] Includes workflow guidance (when to use spec vs impl)
- [ ] Includes sandbox-aware coding guidance (use dynamic ports)
- [ ] References shared observability endpoints
- [ ] Concise enough to fit in AI tool context without dominating it

---

## Task 4.4: M4 E2E verification

**Type:** VALIDATION

**Description:**
Validate the agent-deck integration and kworktree skill work end-to-end.

**Test Steps:**

```bash
# === Part A: Agent-deck integration (requires agent-deck installed) ===

# 1. Setup: create a test project
mkdir -p /tmp/test-kinfra-m4 && cd /tmp/test-kinfra-m4
git init && git commit --allow-empty -m "init"

cat > docker-compose.yml << 'EOF'
services:
  myapp:
    image: python:3.12-slim
    command: python -m http.server 8080
    ports:
      - "${TEST_M4_PORT:-8080}:8080"
EOF
git add . && git commit -m "add compose"

# Create design + milestone
mkdir -p docs/designs/my-feature/implementation
echo "# M1 Foundation" > docs/designs/my-feature/implementation/M1_foundation.md
git add . && git commit -m "add milestone"

# 2. Initialize
kinfra init
# Answer prompts

# 3. Impl with --session
kinfra impl my-feature/M1 --session
# Expected (if agent-deck installed):
#   Worktree created, sandbox started, agent-deck session created
#   Claude started, /kmilestone command sent
# Expected (if agent-deck NOT installed):
#   Worktree created, sandbox started
#   Warning: "agent-deck not found, skipping session management"

# 4. Verify agent-deck session (if installed)
agent-deck list 2>/dev/null && echo "Agent-deck sessions listed" || echo "Agent-deck not available"

# 5. Cleanup
kinfra done my-feature-M1 --force
# Expected: session removed (if agent-deck), sandbox stopped, worktree removed

# 6. Teardown
cd / && rm -rf /tmp/test-kinfra-m4


# === Part B: kworktree skill verification ===

# 1. Verify skill file exists and has expected structure
test -f skills/kworktree/SKILL.md && echo "Skill file exists"

# 2. Check expected sections
grep -q "kinfra init" skills/kworktree/SKILL.md && echo "Has init reference"
grep -q "kinfra spec" skills/kworktree/SKILL.md && echo "Has spec reference"
grep -q "kinfra impl" skills/kworktree/SKILL.md && echo "Has impl reference"
grep -q "kinfra done" skills/kworktree/SKILL.md && echo "Has done reference"
grep -q "kinfra status" skills/kworktree/SKILL.md && echo "Has status reference"
grep -q "observability" skills/kworktree/SKILL.md && echo "Has observability reference"

# 3. Verify it's not too large (should fit in AI context)
wc -l skills/kworktree/SKILL.md
# Expected: under 200 lines (concise enough for context loading)
```

**Success Criteria:**
- [ ] `kinfra impl --session` creates agent-deck session (when available)
- [ ] Session receives `/kmilestone` command
- [ ] `kinfra done` cleans up agent-deck session
- [ ] `--session` degrades gracefully without agent-deck (warning only)
- [ ] kworktree skill file exists with all command references
- [ ] Skill is concise (under 200 lines)
- [ ] Previous milestones (M1, M2) E2E tests still pass

### Completion Checklist

- [ ] All tasks complete and committed
- [ ] Unit tests pass: `uv run pytest tests/unit`
- [ ] Quality gates pass: `uv run ruff check src/ tests/ && uv run mypy src/`
- [ ] E2E test passes (above)
- [ ] M1 + M2 E2E tests still pass
- [ ] No regressions introduced
- [ ] kworktree skill installed via install.sh symlink
