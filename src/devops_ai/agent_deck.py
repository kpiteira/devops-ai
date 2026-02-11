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


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an agent-deck command, logging warnings on failure.

    Never raises — all failures are logged and returned.
    """
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and result.stderr:
        logger.warning(
            "agent-deck command failed: %s — %s",
            " ".join(cmd),
            result.stderr.strip(),
        )
    return result


def add_session(title: str, *, group: str, path: str) -> None:
    """Add an agent-deck session."""
    if not is_available():
        return
    _run_command([
        "agent-deck", "add", path,
        "-t", title,
        "-g", group,
    ])


def remove_session(title: str) -> None:
    """Remove an agent-deck session. Ignores errors (session may not exist)."""
    if not is_available():
        return
    _run_command(["agent-deck", "remove", title])


def start_session(title: str) -> None:
    """Start an agent-deck session (launches Claude in a tmux pane)."""
    if not is_available():
        return
    _run_command(["agent-deck", "session", "start", title])


def send_to_session(title: str, message: str, delay: float = 3) -> None:
    """Send a message to a running agent-deck session.

    Waits ``delay`` seconds before sending to allow the agent to start.
    """
    if not is_available():
        return
    time.sleep(delay)
    _run_command(["agent-deck", "session", "send", title, message])
