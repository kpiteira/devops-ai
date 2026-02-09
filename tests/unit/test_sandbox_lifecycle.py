"""Tests for sandbox lifecycle — start, stop, health gate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from devops_ai.config import InfraConfig, ServicePort
from devops_ai.registry import SlotInfo
from devops_ai.sandbox import (
    run_health_gate,
    start_sandbox,
    stop_sandbox,
)


def _config(
    health_endpoint: str | None = "/health",
    health_port_var: str | None = "API_PORT",
    health_timeout: int = 5,
) -> InfraConfig:
    return InfraConfig(
        project_name="myproj",
        prefix="myproj",
        has_sandbox=True,
        compose_file="docker-compose.yml",
        ports=[ServicePort("API_PORT", 8080)],
        health_endpoint=health_endpoint,
        health_port_var=health_port_var,
        health_timeout=health_timeout,
    )


def _slot(
    slot_id: int = 1,
    slot_dir: str = "/tmp/slot",
    compose_file_copy: str = "/tmp/slot/docker-compose.yml",
) -> SlotInfo:
    return SlotInfo(
        slot_id=slot_id,
        project="myproj",
        worktree_path="/tmp/wt",
        slot_dir=slot_dir,
        compose_file_copy=compose_file_copy,
        ports={"API_PORT": 8081},
        claimed_at="2025-01-01T00:00:00",
        status="running",
    )


class TestStartSandbox:
    def test_command_construction(self, tmp_path: Path) -> None:
        """Verify correct docker compose command with absolute paths."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        # Create the files that start_sandbox references
        compose = wt / "docker-compose.yml"
        compose.write_text("services: {}")
        override = slot_dir / "docker-compose.override.yml"
        override.write_text("services: {}")
        env = slot_dir / ".env.sandbox"
        env.write_text("X=1\n")

        config = _config()
        slot = _slot(
            slot_dir=str(slot_dir),
            compose_file_copy=str(slot_dir / "docker-compose.yml"),
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch(
            "devops_ai.sandbox.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            start_sandbox(config, slot, wt)

        args = mock_run.call_args_list[0]
        cmd = args[0][0]  # first positional arg
        assert "docker" in cmd[0]
        assert "-f" in cmd
        # Compose file from worktree (absolute)
        compose_idx = cmd.index("-f")
        assert str(wt) in cmd[compose_idx + 1]
        # Override from slot dir (absolute)
        second_f = cmd.index("-f", compose_idx + 1)
        assert str(slot_dir) in cmd[second_f + 1]
        # Env file from slot dir
        assert "--env-file" in cmd
        env_idx = cmd.index("--env-file")
        assert str(slot_dir) in cmd[env_idx + 1]
        assert "up" in cmd
        assert "-d" in cmd

    def test_failure_runs_down(self, tmp_path: Path) -> None:
        """Mock compose up failing → compose down called."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()

        config = _config()
        slot = _slot(slot_dir=str(slot_dir))

        # First call (up) fails, second call (down) succeeds
        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stderr = "container failed"
        ok_result = MagicMock()
        ok_result.returncode = 0

        with patch(
            "devops_ai.sandbox.subprocess.run",
            side_effect=[fail_result, ok_result],
        ) as mock_run:
            try:
                start_sandbox(config, slot, wt)
                raise AssertionError("Should have raised")
            except RuntimeError:
                pass

        # Two calls: up then down
        assert mock_run.call_count == 2
        down_cmd = mock_run.call_args_list[1][0][0]
        assert "down" in down_cmd


class TestStopSandbox:
    def test_uses_slot_compose(self, tmp_path: Path) -> None:
        """Verify stop uses slot dir's compose copy, not worktree's."""
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        slot_compose = slot_dir / "docker-compose.yml"
        slot_compose.write_text("services: {}")

        slot = _slot(
            slot_dir=str(slot_dir),
            compose_file_copy=str(slot_compose),
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch(
            "devops_ai.sandbox.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            stop_sandbox(slot)

        cmd = mock_run.call_args[0][0]
        assert "down" in cmd
        # Uses slot compose copy (not worktree)
        f_idx = cmd.index("-f")
        assert str(slot_compose) in cmd[f_idx + 1]


class TestHealthGate:
    def test_success(self) -> None:
        """Mock HTTP 200 → returns True."""
        config = _config(health_timeout=5)
        slot = _slot()

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "devops_ai.sandbox.urllib.request.urlopen",
            return_value=mock_resp,
        ):
            result = run_health_gate(config, slot)
        assert result is True

    def test_timeout(self) -> None:
        """Mock connection refused → returns False after timeout."""
        from urllib.error import URLError

        config = _config(health_timeout=3)
        slot = _slot()

        with patch(
            "devops_ai.sandbox.urllib.request.urlopen",
            side_effect=URLError("Connection refused"),
        ), patch("devops_ai.sandbox.time.sleep"):
            result = run_health_gate(config, slot)
        assert result is False

    def test_url_construction(self) -> None:
        """Correct URL from config + slot ports."""
        config = _config(
            health_endpoint="/api/v1/health",
            health_port_var="API_PORT",
        )
        slot = _slot()  # ports: API_PORT=8081

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "devops_ai.sandbox.urllib.request.urlopen",
            return_value=mock_resp,
        ) as mock_open:
            run_health_gate(config, slot)

        url = mock_open.call_args[0][0]
        assert url == "http://localhost:8081/api/v1/health"
