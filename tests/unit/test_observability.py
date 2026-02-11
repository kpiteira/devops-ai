"""Tests for observability manager — network, compose copy, start/stop/status."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from devops_ai.observability import (
    ObservabilityManager,
    ObservabilityStatus,
    ServiceState,
)


def _mgr(tmp_path: Path) -> ObservabilityManager:
    """Create manager with temp base dir instead of ~/.devops-ai."""
    return ObservabilityManager(base_dir=tmp_path / "observability")


class TestEnsureNetwork:
    def test_creates_network_when_missing(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        inspect_fail = MagicMock(returncode=1)
        create_ok = MagicMock(returncode=0)

        with patch(
            "devops_ai.observability.subprocess.run",
            side_effect=[inspect_fail, create_ok],
        ) as mock_run:
            mgr.ensure_network()

        assert mock_run.call_count == 2
        # First call: inspect
        assert "inspect" in mock_run.call_args_list[0][0][0]
        # Second call: create
        assert "create" in mock_run.call_args_list[1][0][0]

    def test_noop_when_network_exists(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        inspect_ok = MagicMock(returncode=0)

        with patch(
            "devops_ai.observability.subprocess.run",
            return_value=inspect_ok,
        ) as mock_run:
            mgr.ensure_network()

        assert mock_run.call_count == 1
        assert "inspect" in mock_run.call_args[0][0]


class TestEnsureComposeFile:
    def test_copies_template(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        mgr.ensure_compose_file()
        dest = tmp_path / "observability" / "docker-compose.yml"
        assert dest.exists()
        content = dest.read_text()
        assert "devops-ai-jaeger" in content

    def test_idempotent(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        mgr.ensure_compose_file()
        dest = tmp_path / "observability" / "docker-compose.yml"
        # Write sentinel to prove file is not overwritten
        dest.write_text("sentinel")
        mgr.ensure_compose_file()
        assert dest.read_text() == "sentinel"


class TestStart:
    def test_start_command(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        # Pre-create the compose file so ensure_compose_file is a no-op
        mgr.ensure_compose_file()

        mock_result = MagicMock(returncode=0)
        with patch(
            "devops_ai.observability.subprocess.run",
            return_value=mock_result,
        ) as mock_run, patch(
            "devops_ai.observability.urllib.request.urlopen",
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            mgr.start()

        # Find the compose up call (skip network inspect/create calls)
        compose_calls = [
            c for c in mock_run.call_args_list
            if "up" in c[0][0]
        ]
        assert len(compose_calls) == 1
        cmd = compose_calls[0][0][0]
        assert "docker" in cmd[0]
        assert "-f" in cmd
        compose_path = str(tmp_path / "observability" / "docker-compose.yml")
        assert compose_path in cmd


class TestStop:
    def test_stop_command(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        mgr.ensure_compose_file()

        mock_result = MagicMock(returncode=0)
        with patch(
            "devops_ai.observability.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            mgr.stop()

        cmd = mock_run.call_args[0][0]
        assert "down" in cmd
        compose_path = str(tmp_path / "observability" / "docker-compose.yml")
        assert compose_path in cmd


class TestGetEndpoints:
    def test_correct_urls(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        endpoints = mgr.get_endpoints()
        assert endpoints["jaeger_ui"] == "http://localhost:46686"
        assert endpoints["jaeger_otlp"] == "http://localhost:44317"
        assert endpoints["grafana"] == "http://localhost:43000"
        assert endpoints["prometheus"] == "http://localhost:49090"


class TestStatus:
    def test_all_running(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        mgr.ensure_compose_file()

        ps_output = json.dumps([
            {"Service": "devops-ai-jaeger", "State": "running"},
            {"Service": "devops-ai-grafana", "State": "running"},
            {"Service": "devops-ai-prometheus", "State": "running"},
        ])
        mock_result = MagicMock(returncode=0, stdout=ps_output)
        with patch(
            "devops_ai.observability.subprocess.run",
            return_value=mock_result,
        ):
            status = mgr.status()

        assert isinstance(status, ObservabilityStatus)
        assert all(s == ServiceState.RUNNING for s in status.services.values())

    def test_partial(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        mgr.ensure_compose_file()

        ps_output = json.dumps([
            {"Service": "devops-ai-jaeger", "State": "running"},
            {"Service": "devops-ai-grafana", "State": "exited"},
        ])
        mock_result = MagicMock(returncode=0, stdout=ps_output)
        with patch(
            "devops_ai.observability.subprocess.run",
            return_value=mock_result,
        ):
            status = mgr.status()

        assert status.services["devops-ai-jaeger"] == ServiceState.RUNNING
        assert status.services["devops-ai-grafana"] == ServiceState.STOPPED
        assert status.services["devops-ai-prometheus"] == ServiceState.NOT_FOUND


class TestEnsureRunning:
    def test_already_up(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        mgr.ensure_compose_file()

        ps_output = json.dumps([
            {"Service": "devops-ai-jaeger", "State": "running"},
            {"Service": "devops-ai-grafana", "State": "running"},
            {"Service": "devops-ai-prometheus", "State": "running"},
        ])
        mock_result = MagicMock(returncode=0, stdout=ps_output)
        with patch(
            "devops_ai.observability.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            mgr.ensure_running()

        # Only ps call — no up call
        compose_up_calls = [
            c for c in mock_run.call_args_list
            if "up" in c[0][0]
        ]
        assert len(compose_up_calls) == 0

    def test_starts_if_down(self, tmp_path: Path) -> None:
        mgr = _mgr(tmp_path)
        mgr.ensure_compose_file()

        # status() returns partial → start() called
        ps_output = json.dumps([
            {"Service": "devops-ai-jaeger", "State": "running"},
        ])
        mock_result = MagicMock(returncode=0, stdout=ps_output)

        with patch(
            "devops_ai.observability.subprocess.run",
            return_value=mock_result,
        ) as mock_run, patch(
            "devops_ai.observability.urllib.request.urlopen",
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            mgr.ensure_running()

        compose_up_calls = [
            c for c in mock_run.call_args_list
            if "up" in c[0][0]
        ]
        assert len(compose_up_calls) == 1
