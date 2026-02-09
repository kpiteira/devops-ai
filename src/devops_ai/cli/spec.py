"""kinfra spec — Create a spec (design) worktree for a feature."""

from __future__ import annotations

from pathlib import Path

import typer

from devops_ai.config import find_project_root, load_config
from devops_ai.worktree import create_spec_worktree, validate_feature_name


def spec_command(feature: str, repo_root: Path | None = None) -> int:
    """Create a spec worktree. Returns exit code (0=success, 1=error).

    Accepts optional repo_root for testing; defaults to find_project_root()
    or cwd.
    """
    if repo_root is None:
        repo_root = find_project_root() or Path.cwd()

    # Determine prefix: from config or fallback to directory name
    config = load_config(repo_root) if (repo_root / ".devops-ai").is_dir() else None
    prefix = config.prefix if config else repo_root.name

    try:
        validate_feature_name(feature)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        return 1

    try:
        wt_path = create_spec_worktree(repo_root, prefix, feature)
    except Exception as e:
        typer.echo(f"Error creating worktree: {e}", err=True)
        return 1

    typer.echo(f"Created spec worktree: {wt_path}")
    typer.echo(f"  Branch: spec/{feature}")
    typer.echo(f"  Design dir: {wt_path / 'docs' / 'designs' / feature}")
    return 0
