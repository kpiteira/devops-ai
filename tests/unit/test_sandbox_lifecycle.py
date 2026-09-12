"""Tests for sandbox lifecycle — start, stop, health gate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from devops_ai.config import InfraConfig, ServicePort
from devops_ai.registry import SlotInfo
from devops_ai.sandbox import (
    _force_remove_containers,
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
        # Explicit project name: an ambient COMPOSE_PROJECT_NAME can never
        # redirect a destructive down --volumes at another project
        assert cmd[cmd.index("-p") + 1] == "myproj-slot-1"
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
        assert down_cmd[-2:] == ["down", "--volumes"]


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
            result = stop_sandbox(slot)

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "down" in cmd
        # Uses slot compose copy (not worktree)
        f_idx = cmd.index("-f")
        assert str(slot_compose) in cmd[f_idx + 1]

    def test_returns_false_on_compose_down_failure(self, tmp_path: Path) -> None:
        """compose down fails → falls back to force-remove, returns False."""
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        env_file = slot_dir / ".env.sandbox"
        env_file.write_text("COMPOSE_PROJECT_NAME=myproj-slot-1\n")

        slot = _slot(slot_dir=str(slot_dir))

        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stderr = "no such service"

        with (
            patch(
                "devops_ai.sandbox.subprocess.run",
                return_value=fail_result,
            ),
            patch(
                "devops_ai.sandbox._force_remove_containers",
            ) as mock_force,
        ):
            result = stop_sandbox(slot)

        assert result is False
        mock_force.assert_called_once_with("myproj-slot-1")

    def test_returns_false_when_docker_missing(self) -> None:
        """Docker not installed → returns False."""
        slot = _slot()

        with patch(
            "devops_ai.sandbox.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = stop_sandbox(slot)

        assert result is False


class TestForceRemoveContainers:
    def test_removes_matching_containers(self) -> None:
        """Finds and removes containers by project label."""
        ps_result = MagicMock()
        ps_result.stdout = "abc123\ndef456\n"
        rm_result = MagicMock()

        with patch(
            "devops_ai.sandbox.subprocess.run",
            side_effect=[ps_result, rm_result],
        ) as mock_run:
            result = _force_remove_containers("myproj-slot-1")

        assert result is True
        rm_cmd = mock_run.call_args_list[1][0][0]
        assert rm_cmd == ["docker", "rm", "-f", "abc123", "def456"]

    def test_no_containers_found(self) -> None:
        """No matching containers → returns False."""
        ps_result = MagicMock()
        ps_result.stdout = ""

        with patch(
            "devops_ai.sandbox.subprocess.run",
            return_value=ps_result,
        ):
            result = _force_remove_containers("myproj-slot-1")

        assert result is False


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


class TestStopRemovesVolumes:
    def test_down_removes_the_slot_volumes(self, tmp_path: Path) -> None:
        """A slot's named volumes go with its containers (pilot 2026-09-06)."""
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        (slot_dir / ".env.sandbox").write_text("X=1\n")
        slot = SlotInfo(
            slot_id=2, project="p", worktree_path=str(tmp_path),
            slot_dir=str(slot_dir),
            compose_file_copy=str(slot_dir / "docker-compose.yml"),
            ports={}, claimed_at="2025-01-01T00:00:00", status="running",
        )
        with patch("devops_ai.sandbox.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert stop_sandbox(slot) is True
        cmd = mock_run.call_args_list[0][0][0]
        assert cmd[-2:] == ["down", "--volumes"]
        assert cmd[cmd.index("-p") + 1] == "p-slot-2"


class TestStopFallbackRemovesVolumes:
    def test_failed_down_still_removes_volumes(self, tmp_path: Path) -> None:
        """compose down fails → containers AND this project's volumes go."""
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        (slot_dir / ".env.sandbox").write_text("X=1\n")
        slot = SlotInfo(
            slot_id=3, project="p", worktree_path=str(tmp_path),
            slot_dir=str(slot_dir),
            compose_file_copy=str(slot_dir / "docker-compose.yml"),
            ports={}, claimed_at="2025-01-01T00:00:00", status="running",
        )
        down = MagicMock(returncode=1, stderr="boom")
        ps = MagicMock(stdout="c1\n")
        rm = MagicMock()
        vol_ls = MagicMock(stdout="p-slot-3_data\n")
        vol_rm = MagicMock()
        with patch(
            "devops_ai.sandbox.subprocess.run",
            side_effect=[down, ps, rm, vol_ls, vol_rm],
        ) as mock_run:
            assert stop_sandbox(slot) is False
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert cmds[3][:3] == ["docker", "volume", "ls"]
        assert "label=com.docker.compose.project=p-slot-3" in cmds[3]
        assert cmds[4] == ["docker", "volume", "rm", "-f", "p-slot-3_data"]


class TestStartFailureFallsBackToLabels:
    def test_failed_down_after_failed_up_cleans_by_label(
        self, tmp_path: Path
    ) -> None:
        """up fails, down fails → label-based container + volume cleanup."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        (wt / "docker-compose.yml").write_text("services: {}")
        (slot_dir / "docker-compose.override.yml").write_text("services: {}")
        (slot_dir / ".env.sandbox").write_text("X=1\n")
        config = _config()
        slot = _slot(
            slot_dir=str(slot_dir),
            compose_file_copy=str(slot_dir / "docker-compose.yml"),
        )
        up = MagicMock(returncode=1, stderr="up failed")
        down = MagicMock(returncode=1, stderr="down failed")
        ps = MagicMock(stdout="c1\n")
        rm = MagicMock()
        vol_ls = MagicMock(stdout="myproj-slot-1_data\n")
        vol_rm = MagicMock()
        with patch(
            "devops_ai.sandbox.subprocess.run",
            side_effect=[up, down, ps, rm, vol_ls, vol_rm],
        ) as mock_run:
            try:
                start_sandbox(config, slot, wt)
            except RuntimeError:
                pass
            else:
                raise AssertionError("start_sandbox should raise on a failed up")
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert cmds[1][-2:] == ["down", "--volumes"]
        assert cmds[2][:3] == ["docker", "ps", "-a"]
        assert cmds[5] == ["docker", "volume", "rm", "-f", "myproj-slot-1_data"]
