"""Tests for CLI observability commands + impl auto-start."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from devops_ai.cli.observability import (
    _down_command,
    _status_command,
    _up_command,
)
from devops_ai.observability import ObservabilityStatus, ServiceState


class TestObservabilityUp:
    def test_starts_stack(self) -> None:
        """up calls start() and reports endpoints."""
        with patch(
            "devops_ai.cli.observability.ObservabilityManager"
        ) as MockMgr:
            mgr = MockMgr.return_value
            mgr.get_endpoints.return_value = {
                "jaeger_ui": "http://localhost:46686",
                "grafana": "http://localhost:43000",
            }
            # ensure_running raises no error → not already running
            mgr.status.return_value = ObservabilityStatus(
                services={
                    "devops-ai-jaeger": ServiceState.NOT_FOUND,
                    "devops-ai-grafana": ServiceState.NOT_FOUND,
                    "devops-ai-prometheus": ServiceState.NOT_FOUND,
                }
            )
            code, msg = _up_command()

        assert code == 0
        mgr.start.assert_called_once()
        assert "46686" in msg

    def test_already_running(self) -> None:
        """up with all services running → appropriate message."""
        with patch(
            "devops_ai.cli.observability.ObservabilityManager"
        ) as MockMgr:
            mgr = MockMgr.return_value
            mgr.status.return_value = ObservabilityStatus(
                services={
                    "devops-ai-jaeger": ServiceState.RUNNING,
                    "devops-ai-grafana": ServiceState.RUNNING,
                    "devops-ai-prometheus": ServiceState.RUNNING,
                }
            )
            mgr.get_endpoints.return_value = {
                "jaeger_ui": "http://localhost:46686",
            }
            code, msg = _up_command()

        assert code == 0
        mgr.start.assert_not_called()
        assert "already running" in msg.lower()


class TestObservabilityDown:
    def test_warns_active_sandboxes(self) -> None:
        """down warns when sandboxes are still running."""
        mock_registry = MagicMock()
        mock_registry.slots = {
            1: MagicMock(status="running"),
            2: MagicMock(status="stopped"),
        }

        with (
            patch(
                "devops_ai.cli.observability.ObservabilityManager"
            ) as MockMgr,
            patch(
                "devops_ai.cli.observability.load_registry",
                return_value=mock_registry,
            ),
        ):
            mgr = MockMgr.return_value
            code, msg = _down_command()

        assert code == 0
        mgr.stop.assert_called_once()
        assert "1 sandbox" in msg.lower() or "1" in msg


class TestObservabilityStatus:
    def test_display(self) -> None:
        """status returns per-service health."""
        with patch(
            "devops_ai.cli.observability.ObservabilityManager"
        ) as MockMgr:
            mgr = MockMgr.return_value
            mgr.status.return_value = ObservabilityStatus(
                services={
                    "devops-ai-jaeger": ServiceState.RUNNING,
                    "devops-ai-grafana": ServiceState.STOPPED,
                    "devops-ai-prometheus": ServiceState.NOT_FOUND,
                },
                endpoints={
                    "jaeger_ui": "http://localhost:46686",
                    "grafana": "http://localhost:43000",
                    "prometheus": "http://localhost:49090",
                },
            )
            code, msg = _status_command()

        assert code == 0
        assert "jaeger" in msg.lower()
        assert "running" in msg.lower()
        assert "stopped" in msg.lower()


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
                RuntimeError("Docker not running")
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

        # Should succeed despite observability failure
        assert code == 0


# --- Helpers ---


def _setup_git_repo(path: Path) -> None:
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
