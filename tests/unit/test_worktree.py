"""Tests for worktree manager — git worktree lifecycle operations."""

from pathlib import Path

import pytest

from devops_ai.worktree import (
    check_dirty,
    create_spec_worktree,
    impl_branch_name,
    impl_worktree_path,
    list_worktrees,
    remove_worktree,
    spec_branch_name,
    spec_worktree_path,
    validate_feature_name,
)

# --- Pure function tests (no git needed) ---


class TestSpecWorktreePath:
    def test_basic(self) -> None:
        root = Path("/home/user/projects/myapp")
        result = spec_worktree_path(root, "myapp", "my-feature")
        assert result == Path("/home/user/projects/myapp-spec-my-feature")

    def test_custom_prefix(self) -> None:
        root = Path("/home/user/projects/myapp")
        result = spec_worktree_path(root, "khealth", "auth")
        assert result == Path("/home/user/projects/khealth-spec-auth")


class TestImplWorktreePath:
    def test_basic(self) -> None:
        root = Path("/home/user/projects/myapp")
        result = impl_worktree_path(root, "myapp", "my-feature", "M1")
        assert result == Path(
            "/home/user/projects/myapp-impl-my-feature-M1"
        )

    def test_custom_prefix(self) -> None:
        root = Path("/home/user/projects/myapp")
        result = impl_worktree_path(root, "ktrdr", "auth", "M2")
        assert result == Path("/home/user/projects/ktrdr-impl-auth-M2")


class TestSpecBranchName:
    def test_basic(self) -> None:
        assert spec_branch_name("my-feature") == "spec/my-feature"


class TestImplBranchName:
    def test_basic(self) -> None:
        assert impl_branch_name("my-feature", "M1") == (
            "impl/my-feature-M1"
        )


class TestFeatureNameValidation:
    def test_valid_names(self) -> None:
        for name in ["my-feature", "auth", "feature_v2", "ABC-123"]:
            validate_feature_name(name)  # should not raise

    def test_invalid_names(self) -> None:
        for name in [
            "my feature",
            "feat/bar",
            "a@b",
            "",
            "hello world",
            "foo..bar",
        ]:
            with pytest.raises(ValueError):
                validate_feature_name(name)


class TestWorktreePrefixFallback:
    def test_fallback_to_directory_name(self) -> None:
        root = Path("/home/user/projects/myapp")
        # When no config, prefix = directory name
        result = spec_worktree_path(root, root.name, "feat")
        assert result == Path("/home/user/projects/myapp-spec-feat")


# --- Integration tests (require git) ---


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with an initial commit."""
    import subprocess

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
    # Initial commit so branches work
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
