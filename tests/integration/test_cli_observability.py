"""Integration tests for impl auto-start observability (requires git subprocess)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestImplAutoStart:
    def test_impl_calls_ensure_running(self, tmp_path: Path) -> None:
        """impl with sandbox config calls ensure_running()."""
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
            patch("devops_ai.cli.impl.save_registry"),
            patch("devops_ai.cli.impl.create_slot_dir") as mock_sd,
            patch("devops_ai.cli.impl.copy_compose_to_slot") as mock_cc,
            patch("devops_ai.cli.impl.generate_env_file"),
            patch("devops_ai.cli.impl.generate_override"),
            patch("devops_ai.cli.impl.start_sandbox"),
            patch("devops_ai.cli.impl.run_health_gate", return_value=True),
            patch(
                "devops_ai.cli.impl.ObservabilityManager"
            ) as MockObs,
        ):
            mock_wt.return_value = (
                tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
            )
            mock_lr.return_value = MagicMock(slots={})
            mock_alloc.return_value = (1, {"API_PORT": 8081})
            mock_sd.return_value = tmp_path / "slot"
            mock_cc.return_value = tmp_path / "slot" / "docker-compose.yml"

            from devops_ai.cli.impl import impl_command

            code, msg = impl_command("my-feature/M1", repo_root=tmp_path)

        assert code == 0
        MockObs.return_value.ensure_network.assert_called_once()
        MockObs.return_value.ensure_running.assert_called_once()

    def test_impl_ensure_running_failure_non_fatal(
        self, tmp_path: Path
    ) -> None:
        """ensure_running failure is non-fatal — impl continues."""
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
            patch("devops_ai.cli.impl.save_registry"),
            patch("devops_ai.cli.impl.create_slot_dir") as mock_sd,
            patch("devops_ai.cli.impl.copy_compose_to_slot") as mock_cc,
            patch("devops_ai.cli.impl.generate_env_file"),
            patch("devops_ai.cli.impl.generate_override"),
            patch("devops_ai.cli.impl.start_sandbox"),
            patch("devops_ai.cli.impl.run_health_gate", return_value=True),
            patch(
                "devops_ai.cli.impl.ObservabilityManager"
            ) as MockObs,
        ):
            MockObs.return_value.ensure_running.side_effect = (
                RuntimeError("Stack failed to start")
            )
            mock_wt.return_value = (
                tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
            )
            mock_lr.return_value = MagicMock(slots={})
            mock_alloc.return_value = (1, {"API_PORT": 8081})
            mock_sd.return_value = tmp_path / "slot"
            mock_cc.return_value = tmp_path / "slot" / "docker-compose.yml"

            from devops_ai.cli.impl import impl_command

            code, msg = impl_command("my-feature/M1", repo_root=tmp_path)

        # ensure_running failure is non-fatal (network succeeded)
        assert code == 0

    def test_impl_ensure_network_failure_is_fatal(
        self, tmp_path: Path
    ) -> None:
        """ensure_network failure is fatal — impl returns error."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        _setup_infra_toml(tmp_path)
        (tmp_path / "docker-compose.yml").write_text("services: {}\n")

        with (
            patch("devops_ai.cli.impl.create_impl_worktree") as mock_wt,
            patch(
                "devops_ai.cli.impl.ObservabilityManager"
            ) as MockObs,
        ):
            MockObs.return_value.ensure_network.side_effect = (
                RuntimeError("Docker not running")
            )
            mock_wt.return_value = (
                tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
            )

            from devops_ai.cli.impl import impl_command

            code, msg = impl_command("my-feature/M1", repo_root=tmp_path)

        assert code == 1
        assert "observability network" in msg.lower()


# --- Helpers ---


def _setup_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init"], cwd=path, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path, capture_output=True, check=True,
    )


def _setup_milestone(
    repo_root: Path, feature: str, milestone: str
) -> None:
    impl_dir = (
        repo_root / "docs" / "designs" / feature / "implementation"
    )
    impl_dir.mkdir(parents=True, exist_ok=True)
    ms_file = impl_dir / f"{milestone}_foundation.md"
    ms_file.write_text(f"# {milestone} Foundation\n")


def _setup_infra_toml(repo_root: Path) -> None:
    devops_dir = repo_root / ".devops-ai"
    devops_dir.mkdir(exist_ok=True)
    (devops_dir / "infra.toml").write_text(
        '[project]\nname = "test"\nprefix = "test"\n\n'
        '[sandbox]\ncompose_file = "docker-compose.yml"\n\n'
        "[sandbox.ports]\nAPI_PORT = 8080\n"
    )
