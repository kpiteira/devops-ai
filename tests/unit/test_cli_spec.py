"""Tests for kinfra spec CLI command."""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with an initial commit."""
    repo = tmp_path / "main-repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("# test\n")
    subprocess.run(
        ["git", "add", "."], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


class TestSpecInvalidFeatureName:
    def test_exits_with_error(self, git_repo: Path) -> None:
        from devops_ai.cli.spec import spec_command

        exit_code = spec_command("invalid name!", git_repo)
        assert exit_code == 1


class TestSpecWorktreeExists:
    def test_exits_with_error(self, git_repo: Path) -> None:
        from devops_ai.cli.spec import spec_command

        # Create first time — success
        exit_code = spec_command("my-feat", git_repo)
        assert exit_code == 0

        # Create again — should fail (branch already exists)
        exit_code = spec_command("my-feat", git_repo)
        assert exit_code == 1

        # Cleanup
        from devops_ai.worktree import remove_worktree

        wt_path = git_repo.parent / f"{git_repo.name}-spec-my-feat"
        if wt_path.exists():
            remove_worktree(git_repo, wt_path, force=True)
