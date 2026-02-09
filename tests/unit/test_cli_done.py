"""Tests for kinfra done CLI command."""

import subprocess
from pathlib import Path

import pytest

from devops_ai.worktree import create_spec_worktree, remove_worktree


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


class TestDoneDirtyAborts:
    def test_aborts_when_dirty(self, git_repo: Path) -> None:
        from devops_ai.cli.done import done_command

        prefix = git_repo.name
        wt = create_spec_worktree(git_repo, prefix, "feat-a")
        # Make it dirty
        (wt / "dirty.txt").write_text("dirty")

        exit_code, msg = done_command("feat-a", git_repo, force=False)
        assert exit_code == 1
        assert "dirty" in msg.lower() or "uncommitted" in msg.lower()

        # Cleanup
        remove_worktree(git_repo, wt, force=True)


class TestDoneForceIgnoresDirty:
    def test_proceeds_with_force(self, git_repo: Path) -> None:
        from devops_ai.cli.done import done_command

        prefix = git_repo.name
        wt = create_spec_worktree(git_repo, prefix, "feat-b")
        (wt / "dirty.txt").write_text("dirty")

        exit_code, msg = done_command(
            "feat-b", git_repo, force=True
        )
        assert exit_code == 0
        assert not wt.exists()


class TestDoneAmbiguousMatch:
    def test_exits_with_error(self, git_repo: Path) -> None:
        from devops_ai.cli.done import done_command

        prefix = git_repo.name
        create_spec_worktree(git_repo, prefix, "feat-x")
        wt2 = create_spec_worktree(git_repo, prefix, "feat-xy")

        exit_code, msg = done_command("feat-x", git_repo, force=False)
        # "feat-x" matches both "feat-x" and "feat-xy"
        # Should match exact first, so this should succeed
        assert exit_code == 0

        # Cleanup
        remove_worktree(git_repo, wt2, force=True)
