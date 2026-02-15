"""Unit tests for worktree manager — pure function tests (no git needed)."""

from pathlib import Path

import pytest

from devops_ai.worktree import (
    impl_branch_name,
    impl_worktree_path,
    spec_branch_name,
    spec_worktree_path,
    validate_feature_name,
)


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
