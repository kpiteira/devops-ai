"""kinfra status — Show sandbox details for current directory."""

from __future__ import annotations

from pathlib import Path

from devops_ai.config import find_project_root
from devops_ai.registry import get_slot_for_worktree, load_registry


def status_command(cwd: Path | None = None) -> tuple[int, str]:
    """Show sandbox status for the current directory.

    Returns (exit_code, message).
    """
    cwd = cwd or Path.cwd()

    # Find project root
    project_root = find_project_root(cwd)
    if project_root is None:
        return 0, "Not inside a devops-ai project."

    # Check registry for current directory
    registry = load_registry()
    slot = get_slot_for_worktree(registry, cwd)

    if slot is None:
        return 0, "No sandbox running in current directory."

    lines = [
        f"Project:   {slot.project}",
        f"Slot:      {slot.slot_id}",
        f"Status:    {slot.status}",
        f"Worktree:  {slot.worktree_path}",
        f"Slot dir:  {slot.slot_dir}",
        f"Claimed:   {slot.claimed_at}",
    ]
    if slot.ports:
        lines.append("Ports:")
        for env_var, port in sorted(slot.ports.items()):
            lines.append(f"  {env_var}: {port}")

    return 0, "\n".join(lines)
