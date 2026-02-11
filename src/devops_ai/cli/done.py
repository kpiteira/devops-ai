"""kinfra done — Remove a worktree (with sandbox cleanup if applicable)."""

from __future__ import annotations

import logging
from pathlib import Path

from devops_ai.config import find_project_root, load_config
from devops_ai.registry import (
    get_slot_for_worktree,
    load_registry,
    release_slot,
)
from devops_ai.sandbox import remove_slot_dir, stop_sandbox
from devops_ai.worktree import (
    check_dirty,
    list_worktrees,
    remove_worktree,
)

logger = logging.getLogger(__name__)


def done_command(
    name: str,
    repo_root: Path | None = None,
    force: bool = False,
) -> tuple[int, str]:
    """Remove a worktree by name. Returns (exit_code, message).

    If the worktree has an associated sandbox slot, stops containers,
    removes the slot directory, and releases the registry entry before
    removing the worktree.
    """
    if repo_root is None:
        repo_root = find_project_root() or Path.cwd()

    config = (
        load_config(repo_root)
        if (repo_root / ".devops-ai").is_dir()
        else None
    )
    prefix = config.prefix if config else repo_root.name

    # Find matching worktrees
    all_wts = list_worktrees(repo_root, prefix)
    managed = [w for w in all_wts if w.wt_type in ("spec", "impl")]

    # Try exact match first, then partial
    exact = [w for w in managed if w.feature == name]
    if len(exact) == 1:
        matches = exact
    else:
        matches = [w for w in managed if name in w.feature]

    if not matches:
        return 1, f"No worktree found matching '{name}'"

    if len(matches) > 1:
        names = ", ".join(w.feature for w in matches)
        return 1, f"Ambiguous match for '{name}': {names}"

    wt = matches[0]

    # Dirty check (unless forced)
    if not force:
        state = check_dirty(wt.path)
        if state.is_dirty:
            parts = []
            if state.has_uncommitted:
                parts.append("uncommitted changes")
            if state.has_unpushed:
                parts.append("unpushed commits")
            detail = " and ".join(parts)
            return 1, (
                f"Worktree '{wt.feature}' has {detail}. "
                "Use --force to remove anyway."
            )

    # Check registry for sandbox slot
    registry = load_registry()
    slot = get_slot_for_worktree(registry, wt.path)

    if slot is not None:
        # Sandbox cleanup: stop → remove slot dir → release
        slot_dir = Path(slot.slot_dir)
        if slot_dir.exists():
            stop_sandbox(slot)
            remove_slot_dir(slot_dir)
        else:
            logger.warning(
                "Slot dir %s missing, skipping Docker stop",
                slot_dir,
            )
        release_slot(registry, slot.slot_id)

    # Remove worktree
    try:
        remove_worktree(repo_root, wt.path, force=force)
    except Exception as e:
        return 1, f"Error removing worktree: {e}"

    parts = [f"Removed worktree: {wt.feature} ({wt.path})"]
    if slot is not None:
        parts.append(f"  Released slot {slot.slot_id}")
    return 0, "\n".join(parts)
