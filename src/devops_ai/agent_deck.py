"""Agent-deck integration — optional session management via agent-deck CLI."""

from __future__ import annotations

import functools
import logging
import shutil
import subprocess
import time

logger = logging.getLogger(__name__)


class AgentDeckError(Exception):
    """Internal error for agent-deck operations.

    Caught at CLI layer and turned into warnings.
    """


@functools.lru_cache(maxsize=1)
def is_available() -> bool:
    """Check if agent-deck is on PATH. Result is cached for process lifetime."""
    return shutil.which("agent-deck") is not None


COMMAND_TIMEOUT = 60  # seconds; `session send` blocks while the target is busy


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an agent-deck command, logging warnings on failure.

    Never raises — all failures are logged and returned. Bounded by
    ``COMMAND_TIMEOUT`` so a busy target cannot park the caller.
    """
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT
        )
    except FileNotFoundError:
        logger.warning("agent-deck not found on PATH")
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="")
    except subprocess.TimeoutExpired:
        logger.warning(
            "agent-deck command timed out after %ds: %s",
            COMMAND_TIMEOUT, " ".join(cmd),
        )
        return subprocess.CompletedProcess(
            cmd, returncode=1, stdout="", stderr="timed out"
        )
    if result.returncode != 0:
        logger.warning(
            "agent-deck command failed (rc=%s): %s — %s",
            result.returncode,
            " ".join(cmd),
            result.stderr.strip() or "(no output)",
        )
    return result


def add_session(title: str, *, group: str, path: str) -> bool:
    """Add an agent-deck session. Returns True on success."""
    if not is_available():
        return False
    result = _run_command([
        "agent-deck", "add", path,
        "-t", title,
        "-g", group,
    ])
    return result.returncode == 0


def remove_session(title: str) -> None:
    """Remove an agent-deck session. Ignores errors (session may not exist)."""
    if not is_available():
        return
    _run_command(["agent-deck", "remove", title])


def start_session(title: str) -> bool:
    """Start an agent-deck session (launches Claude in a tmux pane)."""
    if not is_available():
        return False
    result = _run_command(["agent-deck", "session", "start", title])
    return result.returncode == 0


def send_to_session(title: str, message: str, delay: float = 3) -> bool:
    """Send a message to a running agent-deck session.

    Waits ``delay`` seconds before sending to allow the agent to start.
    Returns True if agent-deck accepted the message (a busy target times
    out and returns False — the message was NOT delivered).
    """
    if not is_available():
        return False
    time.sleep(delay)
    result = _run_command(["agent-deck", "session", "send", title, message])
    return result.returncode == 0
