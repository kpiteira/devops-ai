"""kinfra done — Remove a worktree (with dirty check)."""

from __future__ import annotations

from pathlib import Path

from devops_ai.config import find_project_root, load_config
from devops_ai.worktree import (
    check_dirty,
    list_worktrees,
    remove_worktree,
)


def done_command(
    name: str,
    repo_root: Path | None = None,
    force: bool = False,
) -> tuple[int, str]:
    """Remove a worktree by name. Returns (exit_code, message)."""
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
    # Filter to spec/impl only (not the main worktree)
    managed = [w for w in all_wts if w.wt_type in ("spec", "impl")]

    # Try exact match first, then partial
    exact = [w for w in managed if w.feature == name]
    if len(exact) == 1:
        matches = exact
    else:
        matches = [w for w in managed if name in w.feature]

    if not matches:
        msg = f"No worktree found matching '{name}'"
        return 1, msg

    if len(matches) > 1:
        names = ", ".join(w.feature for w in matches)
        msg = f"Ambiguous match for '{name}': {names}"
        return 1, msg

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
            msg = (
                f"Worktree '{wt.feature}' has {detail}. "
                "Use --force to remove anyway."
            )
            return 1, msg

    try:
        remove_worktree(repo_root, wt.path, force=force)
    except Exception as e:
        return 1, f"Error removing worktree: {e}"

    msg = f"Removed worktree: {wt.feature} ({wt.path})"
    return 0, msg
