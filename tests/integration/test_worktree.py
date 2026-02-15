"""Integration tests for worktree manager (requires git subprocess)."""

import subprocess
from pathlib import Path

import pytest

from devops_ai.worktree import (
    check_dirty,
    create_spec_worktree,
    list_worktrees,
    remove_worktree,
)


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
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True, capture_output=True,
    )
    # Initial commit so branches work
    (repo / "README.md").write_text("# test\n")
    subprocess.run(
        ["git", "add", "."], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo, check=True, capture_output=True,
    )
    return repo


class TestCreateAndRemoveSpecWorktree:
    def test_full_lifecycle(self, git_repo: Path) -> None:
        prefix = "test"
        wt_path = create_spec_worktree(
            git_repo, prefix, "my-feature"
        )
        assert wt_path.exists()
        assert wt_path.name == "test-spec-my-feature"
        # Design directory created
        assert (wt_path / "docs" / "designs" / "my-feature").is_dir()

        remove_worktree(git_repo, wt_path)
        assert not wt_path.exists()


class TestDirtyCheck:
    def test_uncommitted(self, git_repo: Path) -> None:
        (git_repo / "dirty.txt").write_text("dirty")
        state = check_dirty(git_repo)
        assert state.has_uncommitted is True

    def test_clean(self, git_repo: Path) -> None:
        state = check_dirty(git_repo)
        assert state.has_uncommitted is False
        assert state.has_unpushed is False

    def test_unpushed(self, git_repo: Path) -> None:
        """Unpushed detection requires an upstream — skip if no remote."""
        # Without a remote, has_unpushed should be False (no upstream)
        state = check_dirty(git_repo)
        assert state.has_unpushed is False


class TestListWorktrees:
    def test_list_includes_spec(self, git_repo: Path) -> None:
        prefix = "test"
        create_spec_worktree(git_repo, prefix, "feat-a")
        worktrees = list_worktrees(git_repo, prefix)
        spec_wts = [w for w in worktrees if w.wt_type == "spec"]
        assert len(spec_wts) == 1
        assert spec_wts[0].feature == "feat-a"

        # Cleanup
        remove_worktree(git_repo, spec_wts[0].path)
