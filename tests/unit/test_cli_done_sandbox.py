"""Tests for done command with sandbox cleanup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from devops_ai.cli.done import done_command
from devops_ai.registry import Registry, SlotInfo
from devops_ai.worktree import WorktreeInfo


def _slot(
    slot_id: int = 1,
    worktree_path: str = "/tmp/wt",
    slot_dir: str = "/tmp/slot",
) -> SlotInfo:
    return SlotInfo(
        slot_id=slot_id,
        project="test",
        worktree_path=worktree_path,
        slot_dir=slot_dir,
        compose_file_copy=f"{slot_dir}/docker-compose.yml",
        ports={"API_PORT": 8081},
        claimed_at="2025-01-01T00:00:00",
        status="running",
    )


def _registry_with_slot(slot: SlotInfo) -> Registry:
    return Registry(version=1, slots={slot.slot_id: slot})


def _mock_worktrees(wt_path: Path, prefix: str) -> list[WorktreeInfo]:
    return [
        WorktreeInfo(
            path=wt_path,
            branch="impl/feat-M1",
            wt_type="impl",
            feature="feat-M1",
        ),
    ]


class TestDoneWithSandbox:
    def test_stops_containers(self, tmp_path: Path) -> None:
        """Docker compose down called."""
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        slot = _slot(
            worktree_path=str(wt_path), slot_dir=str(slot_dir)
        )
        registry = _registry_with_slot(slot)

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=_mock_worktrees(wt_path, "test"),
            ),
            patch("devops_ai.cli.done.check_dirty") as mock_dirty,
            patch("devops_ai.cli.done.load_registry", return_value=registry),
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=slot,
            ),
            patch("devops_ai.cli.done.stop_sandbox") as mock_stop,
            patch("devops_ai.cli.done.remove_slot_dir"),
            patch("devops_ai.cli.done.release_slot"),
            patch("devops_ai.cli.done.remove_worktree"),
        ):
            mock_dirty.return_value = MagicMock(is_dirty=False)
            code, msg = done_command("feat-M1", repo_root=tmp_path)

        assert code == 0
        mock_stop.assert_called_once_with(slot)

    def test_removes_slot_dir(self, tmp_path: Path) -> None:
        """Slot dir deleted."""
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        slot = _slot(
            worktree_path=str(wt_path), slot_dir=str(slot_dir)
        )
        registry = _registry_with_slot(slot)

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=_mock_worktrees(wt_path, "test"),
            ),
            patch("devops_ai.cli.done.check_dirty") as mock_dirty,
            patch("devops_ai.cli.done.load_registry", return_value=registry),
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=slot,
            ),
            patch("devops_ai.cli.done.stop_sandbox"),
            patch("devops_ai.cli.done.remove_slot_dir") as mock_rmsd,
            patch("devops_ai.cli.done.release_slot"),
            patch("devops_ai.cli.done.remove_worktree"),
        ):
            mock_dirty.return_value = MagicMock(is_dirty=False)
            code, msg = done_command("feat-M1", repo_root=tmp_path)

        assert code == 0
        mock_rmsd.assert_called_once()

    def test_releases_slot(self, tmp_path: Path) -> None:
        """Registry entry removed."""
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        slot = _slot(worktree_path=str(wt_path))
        registry = _registry_with_slot(slot)

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=_mock_worktrees(wt_path, "test"),
            ),
            patch("devops_ai.cli.done.check_dirty") as mock_dirty,
            patch("devops_ai.cli.done.load_registry", return_value=registry),
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=slot,
            ),
            patch("devops_ai.cli.done.stop_sandbox"),
            patch("devops_ai.cli.done.remove_slot_dir"),
            patch("devops_ai.cli.done.release_slot") as mock_rel,
            patch("devops_ai.cli.done.remove_worktree"),
        ):
            mock_dirty.return_value = MagicMock(is_dirty=False)
            code, msg = done_command("feat-M1", repo_root=tmp_path)

        assert code == 0
        mock_rel.assert_called_once()

    def test_ordering_stop_before_remove(self, tmp_path: Path) -> None:
        """Stop containers before remove worktree."""
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        slot = _slot(
            worktree_path=str(wt_path), slot_dir=str(slot_dir)
        )
        registry = _registry_with_slot(slot)
        call_order: list[str] = []

        def track_stop(*a, **kw):  # noqa: ANN002, ANN003
            call_order.append("stop")

        def track_remove(*a, **kw):  # noqa: ANN002, ANN003
            call_order.append("remove_wt")

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=_mock_worktrees(wt_path, "test"),
            ),
            patch("devops_ai.cli.done.check_dirty") as mock_dirty,
            patch("devops_ai.cli.done.load_registry", return_value=registry),
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=slot,
            ),
            patch(
                "devops_ai.cli.done.stop_sandbox", side_effect=track_stop
            ),
            patch("devops_ai.cli.done.remove_slot_dir"),
            patch("devops_ai.cli.done.release_slot"),
            patch(
                "devops_ai.cli.done.remove_worktree",
                side_effect=track_remove,
            ),
        ):
            mock_dirty.return_value = MagicMock(is_dirty=False)
            done_command("feat-M1", repo_root=tmp_path)

        assert call_order == ["stop", "remove_wt"]

    def test_missing_slot_dir_graceful(self, tmp_path: Path) -> None:
        """Slot dir missing → skip Docker stop, still clean registry."""
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        slot = _slot(
            worktree_path=str(wt_path),
            slot_dir="/nonexistent/slot",
        )
        registry = _registry_with_slot(slot)

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=_mock_worktrees(wt_path, "test"),
            ),
            patch("devops_ai.cli.done.check_dirty") as mock_dirty,
            patch("devops_ai.cli.done.load_registry", return_value=registry),
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=slot,
            ),
            patch("devops_ai.cli.done.stop_sandbox") as mock_stop,
            patch("devops_ai.cli.done.remove_slot_dir"),
            patch("devops_ai.cli.done.release_slot") as mock_rel,
            patch("devops_ai.cli.done.remove_worktree"),
        ):
            mock_dirty.return_value = MagicMock(is_dirty=False)
            code, msg = done_command("feat-M1", repo_root=tmp_path)

        assert code == 0
        # Stop should NOT be called (slot dir missing)
        mock_stop.assert_not_called()
        # But release should still happen
        mock_rel.assert_called_once()

    def test_spec_worktree_no_sandbox(self, tmp_path: Path) -> None:
        """Spec worktree without sandbox → same as M1 behavior."""
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()

        spec_wt = WorktreeInfo(
            path=wt_path,
            branch="spec/my-feature",
            wt_type="spec",
            feature="my-feature",
        )

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=[spec_wt],
            ),
            patch("devops_ai.cli.done.check_dirty") as mock_dirty,
            patch("devops_ai.cli.done.load_registry") as mock_lr,
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=None,
            ),
            patch("devops_ai.cli.done.remove_worktree"),
        ):
            mock_dirty.return_value = MagicMock(is_dirty=False)
            mock_lr.return_value = Registry(version=1, slots={})
            code, msg = done_command("my-feature", repo_root=tmp_path)

        assert code == 0
        assert "removed" in msg.lower()
