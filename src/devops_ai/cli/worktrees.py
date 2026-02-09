"""kinfra worktrees — List all active worktrees."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from devops_ai.config import find_project_root, load_config
from devops_ai.worktree import list_worktrees


def worktrees_command(repo_root: Path | None = None) -> int:
    """List all active worktrees. Returns exit code."""
    if repo_root is None:
        repo_root = find_project_root() or Path.cwd()

    config = (
        load_config(repo_root)
        if (repo_root / ".devops-ai").is_dir()
        else None
    )
    prefix = config.prefix if config else repo_root.name
    project_name = config.project_name if config else repo_root.name

    all_wts = list_worktrees(repo_root, prefix)
    managed = [w for w in all_wts if w.wt_type in ("spec", "impl")]

    if not managed:
        typer.echo("No active worktrees.")
        return 0

    table = Table(title=f"Worktrees — {project_name}")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Branch", style="yellow")
    table.add_column("Path")

    for wt in managed:
        table.add_row(
            wt.feature,
            wt.wt_type,
            wt.branch,
            str(wt.path),
        )

    console = Console()
    console.print(table)
    return 0
