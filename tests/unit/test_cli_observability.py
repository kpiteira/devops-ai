"""Unit tests for CLI observability commands (pure, all mocked)."""

from __future__ import annotations

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
