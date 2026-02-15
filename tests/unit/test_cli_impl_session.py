"""Unit tests for session title helper (pure functions only)."""

from __future__ import annotations

from unittest.mock import MagicMock

from devops_ai.cli.done import _session_title_from_worktree


class TestSessionTitleFromWorktree:
    """Unit tests for _session_title_from_worktree helper."""

    def test_impl_branch(self) -> None:
        """impl/feat-M1 → feat/M1."""
        wt = MagicMock()
        wt.branch = "impl/my-feature-M1"
        assert _session_title_from_worktree(wt) == "my-feature/M1"

    def test_impl_branch_phase(self) -> None:
        """impl/feat-Phase2 → feat/Phase2."""
        wt = MagicMock()
        wt.branch = "impl/my-feature-Phase2"
        assert _session_title_from_worktree(wt) == "my-feature/Phase2"

    def test_spec_branch(self) -> None:
        """spec/feat → spec/feat."""
        wt = MagicMock()
        wt.branch = "spec/my-feature"
        assert _session_title_from_worktree(wt) == "spec/my-feature"

    def test_fallback_no_branch(self) -> None:
        """No branch → use wt.feature."""
        wt = MagicMock()
        wt.branch = ""
        wt.feature = "my-feature"
        assert _session_title_from_worktree(wt) == "my-feature"

    def test_multi_hyphen_impl(self) -> None:
        """impl/my-cool-feature-M3 → my-cool-feature/M3."""
        wt = MagicMock()
        wt.branch = "impl/my-cool-feature-M3"
        assert _session_title_from_worktree(wt) == "my-cool-feature/M3"
