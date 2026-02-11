"""Tests for agent-deck integration module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from devops_ai.agent_deck import (
    add_session,
    is_available,
    remove_session,
    send_to_session,
    start_session,
)


class TestIsAvailable:
    def setup_method(self) -> None:
        """Reset the cached availability between tests."""
        # Clear the lru_cache or module-level cache
        is_available.cache_clear()

    def test_found(self) -> None:
        """shutil.which returns path → True."""
        with patch(
            "devops_ai.agent_deck.shutil.which",
            return_value="/usr/bin/agent-deck",
        ):
            assert is_available() is True

    def test_not_found(self) -> None:
        """shutil.which returns None → False."""
        with patch("devops_ai.agent_deck.shutil.which", return_value=None):
            assert is_available() is False

    def test_cached(self) -> None:
        """Result is cached — shutil.which called only once."""
        with patch(
            "devops_ai.agent_deck.shutil.which",
            return_value="/usr/bin/agent-deck",
        ) as mock_which:
            assert is_available() is True
            assert is_available() is True
            mock_which.assert_called_once()


class TestAddSession:
    def test_command(self) -> None:
        """Verify correct command construction."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            add_session("my-feature/M1", group="dev", path="/tmp/worktree")

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd == [
                "agent-deck", "add", "/tmp/worktree",
                "-t", "my-feature/M1",
                "-g", "dev",
            ]

    def test_spec_naming(self) -> None:
        """Spec feature → title=spec/<feature>, group=dev."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            add_session(
                "spec/wellness-reminders",
                group="dev",
                path="/tmp/wt",
            )

            cmd = mock_run.call_args[0][0]
            # path is positional, title via -t, group via -g
            assert cmd[2] == "/tmp/wt"
            assert cmd[4] == "spec/wellness-reminders"
            assert cmd[6] == "dev"

    def test_impl_naming(self) -> None:
        """Impl feature/milestone → title=<feature>/<milestone>."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            add_session(
                "wellness-reminders/M1",
                group="dev",
                path="/tmp/wt",
            )

            cmd = mock_run.call_args[0][0]
            assert cmd[4] == "wellness-reminders/M1"
            assert cmd[6] == "dev"


class TestRemoveSession:
    def test_command(self) -> None:
        """Verify correct remove command."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            remove_session("my-feature/M1")

            cmd = mock_run.call_args[0][0]
            assert cmd == ["agent-deck", "remove", "my-feature/M1"]

    def test_ignores_errors(self) -> None:
        """subprocess fails → no exception raised."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=1, stderr="session not found"
            )
            # Should not raise
            remove_session("nonexistent")


class TestStartSession:
    def test_command(self) -> None:
        """Verify correct start command."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            start_session("my-feature/M1")

            cmd = mock_run.call_args[0][0]
            assert cmd == ["agent-deck", "session", "start", "my-feature/M1"]


class TestSendToSession:
    def test_command(self) -> None:
        """Verify correct send command."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
            patch("devops_ai.agent_deck.time.sleep"),
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            msg = "/kmilestone my-feature/M1"
            send_to_session("my-feature/M1", msg, delay=3)

            cmd = mock_run.call_args[0][0]
            assert cmd == [
                "agent-deck", "session", "send",
                "my-feature/M1", msg,
            ]

    def test_delay(self) -> None:
        """Verify delay parameter is used."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
            patch("devops_ai.agent_deck.time.sleep") as mock_sleep,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            send_to_session("title", "msg", delay=5)
            mock_sleep.assert_called_once_with(5)

    def test_default_delay(self) -> None:
        """Default delay is 3 seconds."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
            patch("devops_ai.agent_deck.time.sleep") as mock_sleep,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            send_to_session("title", "msg")
            mock_sleep.assert_called_once_with(3)


class TestSkipWhenUnavailable:
    def test_all_ops_skip(self) -> None:
        """Every function returns early when agent-deck not available."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=False),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
        ):
            add_session("title", group="dev", path="/tmp")
            remove_session("title")
            start_session("title")
            send_to_session("title", "msg")
            mock_run.assert_not_called()


class TestSubprocessFailureWarns:
    def test_warns_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """Subprocess failure → warning logged, no exception."""
        with (
            patch("devops_ai.agent_deck.is_available", return_value=True),
            patch("devops_ai.agent_deck.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=1, stderr="something went wrong"
            )
            import logging

            with caplog.at_level(logging.WARNING):
                start_session("my-feature/M1")

            assert "something went wrong" in caplog.text
