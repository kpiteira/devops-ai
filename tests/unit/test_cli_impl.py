"""Tests for CLI impl command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from devops_ai.cli.impl import impl_command, parse_feature_milestone


class TestParseFeatureMilestone:
    def test_simple(self) -> None:
        feature, milestone = parse_feature_milestone("wellness-reminders/M1")
        assert feature == "wellness-reminders"
        assert milestone == "M1"

    def test_no_slash(self) -> None:
        """Missing slash → error."""
        try:
            parse_feature_milestone("no-slash")
            raise AssertionError("Should have raised")
        except ValueError as e:
            assert "feature/milestone" in str(e).lower()


class TestMilestoneNotFound:
    def test_error_message(self, tmp_path: Path) -> None:
        """Missing milestone file → informative error."""
        _setup_git_repo(tmp_path)
        code, msg = impl_command(
            "my-feature/M99", repo_root=tmp_path
        )
        assert code == 1
        assert "milestone" in msg.lower() or "not found" in msg.lower()


class TestWorktreeAlreadyExists:
    def test_error_message(self, tmp_path: Path) -> None:
        """Worktree path already exists → error."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        # Pre-create the worktree directory
        wt_path = tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
        wt_path.mkdir()

        code, msg = impl_command(
            "my-feature/M1", repo_root=tmp_path
        )
        assert code == 1
        assert "already exists" in msg.lower()


class TestImplWithoutConfig:
    def test_creates_worktree_only(self, tmp_path: Path) -> None:
        """No infra.toml → worktree only, no sandbox."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")

        with patch(
            "devops_ai.cli.impl.create_impl_worktree"
        ) as mock_create:
            mock_create.return_value = (
                tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
            )
            code, msg = impl_command(
                "my-feature/M1", repo_root=tmp_path
            )
        assert code == 0
        mock_create.assert_called_once()
        assert "worktree" in msg.lower()


class TestImplWithConfig:
    def test_allocates_slot(self, tmp_path: Path) -> None:
        """With sandbox config → slot claimed in registry."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        _setup_infra_toml(tmp_path)
        # Create compose file
        (tmp_path / "docker-compose.yml").write_text("services: {}\n")

        with (
            patch("devops_ai.cli.impl.create_impl_worktree") as mock_wt,
            patch("devops_ai.cli.impl.load_registry") as mock_lr,
            patch("devops_ai.cli.impl.allocate_slot") as mock_alloc,
            patch("devops_ai.cli.impl.clean_stale_entries"),
            patch("devops_ai.cli.impl.claim_slot") as mock_claim,
            patch("devops_ai.cli.impl.create_slot_dir") as mock_sd,
            patch("devops_ai.cli.impl.copy_compose_to_slot") as mock_cc,
            patch("devops_ai.cli.impl.generate_env_file"),
            patch("devops_ai.cli.impl.generate_override"),
            patch("devops_ai.cli.impl.start_sandbox"),
            patch("devops_ai.cli.impl.run_health_gate", return_value=True),
        ):
            mock_wt.return_value = (
                tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
            )
            mock_lr.return_value = MagicMock(slots={})
            mock_alloc.return_value = (1, {"API_PORT": 8081})
            mock_sd.return_value = tmp_path / "slot"
            mock_cc.return_value = tmp_path / "slot" / "docker-compose.yml"

            code, msg = impl_command(
                "my-feature/M1", repo_root=tmp_path
            )

        assert code == 0
        mock_claim.assert_called_once()


class TestImplDockerFailure:
    def test_releases_slot_keeps_worktree(self, tmp_path: Path) -> None:
        """Docker failure → slot released, worktree kept."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        _setup_infra_toml(tmp_path)
        (tmp_path / "docker-compose.yml").write_text("services: {}\n")

        with (
            patch("devops_ai.cli.impl.create_impl_worktree") as mock_wt,
            patch("devops_ai.cli.impl.load_registry") as mock_lr,
            patch("devops_ai.cli.impl.allocate_slot") as mock_alloc,
            patch("devops_ai.cli.impl.clean_stale_entries"),
            patch("devops_ai.cli.impl.claim_slot"),
            patch("devops_ai.cli.impl.release_slot") as mock_release,
            patch("devops_ai.cli.impl.create_slot_dir") as mock_sd,
            patch("devops_ai.cli.impl.copy_compose_to_slot") as mock_cc,
            patch("devops_ai.cli.impl.generate_env_file"),
            patch("devops_ai.cli.impl.generate_override"),
            patch(
                "devops_ai.cli.impl.start_sandbox",
                side_effect=RuntimeError("Docker failed"),
            ),
            patch("devops_ai.cli.impl.remove_slot_dir"),
        ):
            mock_wt.return_value = (
                tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
            )
            mock_lr.return_value = MagicMock(slots={})
            mock_alloc.return_value = (1, {"API_PORT": 8081})
            mock_sd.return_value = tmp_path / "slot"
            mock_cc.return_value = tmp_path / "slot" / "docker-compose.yml"

            code, msg = impl_command(
                "my-feature/M1", repo_root=tmp_path
            )

        assert code == 1
        mock_release.assert_called_once()
        # Worktree should NOT have been removed
        assert "worktree preserved" in msg.lower()


# --- Helpers ---


def _setup_git_repo(path: Path) -> None:
    """Create a minimal git repo."""
    import subprocess

    subprocess.run(
        ["git", "init"], cwd=path, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path,
        capture_output=True,
        check=True,
    )


def _setup_milestone(
    repo_root: Path, feature: str, milestone: str
) -> None:
    """Create a milestone file in the expected location."""
    impl_dir = (
        repo_root / "docs" / "designs" / feature / "implementation"
    )
    impl_dir.mkdir(parents=True, exist_ok=True)
    ms_file = impl_dir / f"{milestone}_foundation.md"
    ms_file.write_text(f"# {milestone} Foundation\n")


def _setup_infra_toml(repo_root: Path) -> None:
    """Create a minimal infra.toml with sandbox config."""
    devops_dir = repo_root / ".devops-ai"
    devops_dir.mkdir(exist_ok=True)
    (devops_dir / "infra.toml").write_text(
        '[project]\nname = "test"\nprefix = "test"\n\n'
        '[sandbox]\ncompose_file = "docker-compose.yml"\n\n'
        "[sandbox.ports]\nAPI_PORT = 8080\n"
    )
