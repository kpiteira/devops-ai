"""Worktree manager — git worktree lifecycle operations."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

FEATURE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class DirtyState:
    """Result of checking a worktree for uncommitted/unpushed changes."""

    has_uncommitted: bool = False
    has_unpushed: bool = False

    @property
    def is_dirty(self) -> bool:
        return self.has_uncommitted or self.has_unpushed


@dataclass
class WorktreeInfo:
    """Information about an active git worktree."""

    path: Path
    branch: str
    wt_type: str  # "spec", "impl", or "other"
    feature: str  # extracted feature name, or "" if unknown


def validate_feature_name(name: str) -> None:
    """Validate feature name matches allowed pattern."""
    if not name or not FEATURE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid feature name: {name!r}. "
            "Must match [a-zA-Z0-9_-]+"
        )


def spec_worktree_path(
    repo_root: Path, prefix: str, feature: str
) -> Path:
    """Compute the path for a spec worktree."""
    return repo_root.parent / f"{prefix}-spec-{feature}"


def impl_worktree_path(
    repo_root: Path, prefix: str, feature: str, milestone: str
) -> Path:
    """Compute the path for an impl worktree."""
    return repo_root.parent / f"{prefix}-impl-{feature}-{milestone}"


def spec_branch_name(feature: str) -> str:
    """Compute the branch name for a spec worktree."""
    return f"spec/{feature}"


def impl_branch_name(feature: str, milestone: str) -> str:
    """Compute the branch name for an impl worktree."""
    return f"impl/{feature}-{milestone}"


def _run_git(
    args: list[str], cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def create_spec_worktree(
    repo_root: Path, prefix: str, feature: str
) -> Path:
    """Create a spec worktree and its design directory."""
    validate_feature_name(feature)
    wt_path = spec_worktree_path(repo_root, prefix, feature)
    branch = spec_branch_name(feature)

    _run_git(
        ["worktree", "add", "-b", branch, str(wt_path)],
        cwd=repo_root,
    )

    # Create design directory in the worktree
    design_dir = wt_path / "docs" / "designs" / feature
    design_dir.mkdir(parents=True, exist_ok=True)

    return wt_path


def create_impl_worktree(
    repo_root: Path, prefix: str, feature: str, milestone: str
) -> Path:
    """Create an impl worktree."""
    validate_feature_name(feature)
    wt_path = impl_worktree_path(
        repo_root, prefix, feature, milestone
    )
    branch = impl_branch_name(feature, milestone)

    _run_git(
        ["worktree", "add", "-b", branch, str(wt_path)],
        cwd=repo_root,
    )

    return wt_path


def remove_worktree(
    repo_root: Path, wt_path: Path, force: bool = False
) -> None:
    """Remove a git worktree."""
    args = ["worktree", "remove", str(wt_path)]
    if force:
        args.append("--force")
    _run_git(args, cwd=repo_root)


def check_dirty(path: Path) -> DirtyState:
    """Check a worktree for uncommitted changes and unpushed commits."""
    # Uncommitted changes
    result = _run_git(
        ["status", "--porcelain"], cwd=path, check=False
    )
    has_uncommitted = bool(result.stdout.strip())

    # Unpushed commits (only if upstream exists)
    has_unpushed = False
    upstream = _run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=path,
        check=False,
    )
    if upstream.returncode == 0:
        unpushed = _run_git(
            ["log", "@{u}..HEAD", "--oneline"],
            cwd=path,
            check=False,
        )
        has_unpushed = bool(unpushed.stdout.strip())

    return DirtyState(
        has_uncommitted=has_uncommitted,
        has_unpushed=has_unpushed,
    )


def list_worktrees(
    repo_root: Path, prefix: str
) -> list[WorktreeInfo]:
    """List all worktrees, identifying spec/impl by prefix matching."""
    result = _run_git(
        ["worktree", "list", "--porcelain"], cwd=repo_root
    )

    worktrees: list[WorktreeInfo] = []
    current_path: Path | None = None
    current_branch = ""

    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.split(" ", 1)[1])
        elif line.startswith("branch "):
            # e.g., "branch refs/heads/spec/my-feature"
            ref = line.split(" ", 1)[1]
            current_branch = ref.removeprefix("refs/heads/")
        elif line == "":
            if current_path is not None:
                wt_type, feature = _classify_worktree(
                    current_path, prefix
                )
                worktrees.append(
                    WorktreeInfo(
                        path=current_path,
                        branch=current_branch,
                        wt_type=wt_type,
                        feature=feature,
                    )
                )
                current_path = None
                current_branch = ""

    # Handle last entry (porcelain output may not end with blank line)
    if current_path is not None:
        wt_type, feature = _classify_worktree(current_path, prefix)
        worktrees.append(
            WorktreeInfo(
                path=current_path,
                branch=current_branch,
                wt_type=wt_type,
                feature=feature,
            )
        )

    return worktrees


def _classify_worktree(
    path: Path, prefix: str
) -> tuple[str, str]:
    """Classify a worktree as spec/impl/other based on directory name."""
    name = path.name
    spec_prefix = f"{prefix}-spec-"
    impl_prefix = f"{prefix}-impl-"

    if name.startswith(spec_prefix):
        return "spec", name[len(spec_prefix) :]
    if name.startswith(impl_prefix):
        return "impl", name[len(impl_prefix) :]
    return "other", ""
