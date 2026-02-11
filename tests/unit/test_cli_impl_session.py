"""Tests for --session flag integration in impl and done commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from devops_ai.cli.done import _session_title_from_worktree, done_command
from devops_ai.cli.impl import impl_command

# --- Helpers ---


def _setup_git_repo(path: Path) -> None:
    """Create a minimal git repo."""
    import subprocess

    subprocess.run(
        ["git", "init"], cwd=path, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path, check=True, capture_output=True,
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
    """Create a milestone file."""
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


def _mock_sandbox_setup() -> dict:
    """Return a dict of patches for sandbox setup mocking."""
    return {
        "create_impl_worktree": "devops_ai.cli.impl.create_impl_worktree",
        "load_registry": "devops_ai.cli.impl.load_registry",
        "allocate_slot": "devops_ai.cli.impl.allocate_slot",
        "clean_stale": "devops_ai.cli.impl.clean_stale_entries",
        "claim_slot": "devops_ai.cli.impl.claim_slot",
        "create_slot_dir": "devops_ai.cli.impl.create_slot_dir",
        "copy_compose": "devops_ai.cli.impl.copy_compose_to_slot",
        "gen_env": "devops_ai.cli.impl.generate_env_file",
        "gen_override": "devops_ai.cli.impl.generate_override",
        "start_sandbox": "devops_ai.cli.impl.start_sandbox",
        "health_gate": "devops_ai.cli.impl.run_health_gate",
    }


class TestSessionFlagWithAgentDeck:
    def test_all_three_calls_in_order(
        self, tmp_path: Path
    ) -> None:
        """--session with agent-deck: add, start, send called."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        _setup_infra_toml(tmp_path)
        (tmp_path / "docker-compose.yml").write_text(
            "services: {}\n"
        )

        wt_path = (
            tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
        )

        with (
            patch(
                "devops_ai.cli.impl.create_impl_worktree",
                return_value=wt_path,
            ),
            patch("devops_ai.cli.impl.load_registry") as mock_lr,
            patch(
                "devops_ai.cli.impl.allocate_slot",
                return_value=(1, {"API_PORT": 8081}),
            ),
            patch("devops_ai.cli.impl.clean_stale_entries"),
            patch("devops_ai.cli.impl.claim_slot"),
            patch(
                "devops_ai.cli.impl.create_slot_dir",
                return_value=tmp_path / "slot",
            ),
            patch(
                "devops_ai.cli.impl.copy_compose_to_slot",
                return_value=tmp_path / "slot" / "docker-compose.yml",
            ),
            patch("devops_ai.cli.impl.generate_env_file"),
            patch("devops_ai.cli.impl.generate_override"),
            patch("devops_ai.cli.impl.start_sandbox"),
            patch(
                "devops_ai.cli.impl.run_health_gate",
                return_value=True,
            ),
            patch(
                "devops_ai.cli.impl.agent_deck"
            ) as mock_ad,
        ):
            mock_lr.return_value = MagicMock(slots={})
            mock_ad.is_available.return_value = True

            code, msg = impl_command(
                "my-feature/M1",
                repo_root=tmp_path,
                session=True,
            )

        assert code == 0
        mock_ad.add_session.assert_called_once()
        mock_ad.start_session.assert_called_once()
        mock_ad.send_to_session.assert_called_once()

        # Verify order: add → start → send
        ad_calls = mock_ad.method_calls
        call_names = [c[0] for c in ad_calls if c[0] != "is_available"]
        assert call_names == [
            "add_session", "start_session", "send_to_session"
        ]


class TestSessionFlagWithoutAgentDeck:
    def test_warning_printed_impl_succeeds(
        self, tmp_path: Path
    ) -> None:
        """--session without agent-deck: warning, but impl OK."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        _setup_infra_toml(tmp_path)
        (tmp_path / "docker-compose.yml").write_text(
            "services: {}\n"
        )

        wt_path = (
            tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
        )

        with (
            patch(
                "devops_ai.cli.impl.create_impl_worktree",
                return_value=wt_path,
            ),
            patch("devops_ai.cli.impl.load_registry") as mock_lr,
            patch(
                "devops_ai.cli.impl.allocate_slot",
                return_value=(1, {"API_PORT": 8081}),
            ),
            patch("devops_ai.cli.impl.clean_stale_entries"),
            patch("devops_ai.cli.impl.claim_slot"),
            patch(
                "devops_ai.cli.impl.create_slot_dir",
                return_value=tmp_path / "slot",
            ),
            patch(
                "devops_ai.cli.impl.copy_compose_to_slot",
                return_value=tmp_path / "slot" / "docker-compose.yml",
            ),
            patch("devops_ai.cli.impl.generate_env_file"),
            patch("devops_ai.cli.impl.generate_override"),
            patch("devops_ai.cli.impl.start_sandbox"),
            patch(
                "devops_ai.cli.impl.run_health_gate",
                return_value=True,
            ),
            patch(
                "devops_ai.cli.impl.agent_deck"
            ) as mock_ad,
        ):
            mock_lr.return_value = MagicMock(slots={})
            mock_ad.is_available.return_value = False

            code, msg = impl_command(
                "my-feature/M1",
                repo_root=tmp_path,
                session=True,
            )

        assert code == 0
        assert "agent-deck not found" in msg.lower()
        mock_ad.add_session.assert_not_called()


class TestSessionSendDelay:
    def test_delay_parameter_passed(
        self, tmp_path: Path
    ) -> None:
        """send_to_session receives delay=3."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        _setup_infra_toml(tmp_path)
        (tmp_path / "docker-compose.yml").write_text(
            "services: {}\n"
        )

        wt_path = (
            tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
        )

        with (
            patch(
                "devops_ai.cli.impl.create_impl_worktree",
                return_value=wt_path,
            ),
            patch("devops_ai.cli.impl.load_registry") as mock_lr,
            patch(
                "devops_ai.cli.impl.allocate_slot",
                return_value=(1, {"API_PORT": 8081}),
            ),
            patch("devops_ai.cli.impl.clean_stale_entries"),
            patch("devops_ai.cli.impl.claim_slot"),
            patch(
                "devops_ai.cli.impl.create_slot_dir",
                return_value=tmp_path / "slot",
            ),
            patch(
                "devops_ai.cli.impl.copy_compose_to_slot",
                return_value=tmp_path / "slot" / "docker-compose.yml",
            ),
            patch("devops_ai.cli.impl.generate_env_file"),
            patch("devops_ai.cli.impl.generate_override"),
            patch("devops_ai.cli.impl.start_sandbox"),
            patch(
                "devops_ai.cli.impl.run_health_gate",
                return_value=True,
            ),
            patch(
                "devops_ai.cli.impl.agent_deck"
            ) as mock_ad,
        ):
            mock_lr.return_value = MagicMock(slots={})
            mock_ad.is_available.return_value = True

            impl_command(
                "my-feature/M1",
                repo_root=tmp_path,
                session=True,
            )

        # Check delay=3 passed to send_to_session
        send_call = mock_ad.send_to_session.call_args
        assert send_call[1].get("delay") == 3 or (
            len(send_call[0]) >= 3 and send_call[0][2] == 3
        )


class TestSessionSendCorrectCommand:
    def test_kmilestone_command_sent(
        self, tmp_path: Path
    ) -> None:
        """/kmilestone <feature>/<milestone> sent."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        _setup_infra_toml(tmp_path)
        (tmp_path / "docker-compose.yml").write_text(
            "services: {}\n"
        )

        wt_path = (
            tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
        )

        with (
            patch(
                "devops_ai.cli.impl.create_impl_worktree",
                return_value=wt_path,
            ),
            patch("devops_ai.cli.impl.load_registry") as mock_lr,
            patch(
                "devops_ai.cli.impl.allocate_slot",
                return_value=(1, {"API_PORT": 8081}),
            ),
            patch("devops_ai.cli.impl.clean_stale_entries"),
            patch("devops_ai.cli.impl.claim_slot"),
            patch(
                "devops_ai.cli.impl.create_slot_dir",
                return_value=tmp_path / "slot",
            ),
            patch(
                "devops_ai.cli.impl.copy_compose_to_slot",
                return_value=tmp_path / "slot" / "docker-compose.yml",
            ),
            patch("devops_ai.cli.impl.generate_env_file"),
            patch("devops_ai.cli.impl.generate_override"),
            patch("devops_ai.cli.impl.start_sandbox"),
            patch(
                "devops_ai.cli.impl.run_health_gate",
                return_value=True,
            ),
            patch(
                "devops_ai.cli.impl.agent_deck"
            ) as mock_ad,
        ):
            mock_lr.return_value = MagicMock(slots={})
            mock_ad.is_available.return_value = True

            impl_command(
                "my-feature/M1",
                repo_root=tmp_path,
                session=True,
            )

        send_call = mock_ad.send_to_session.call_args
        # First positional arg is title, second is message
        assert send_call[0][1] == "/kmilestone my-feature/M1"


class TestDoneRemovesSession:
    def test_remove_called(self, tmp_path: Path) -> None:
        """done calls agent_deck.remove_session with slash-separated title."""
        _setup_git_repo(tmp_path)
        _setup_infra_toml(tmp_path)

        mock_wt = MagicMock()
        mock_wt.feature = "my-feature-M1"
        mock_wt.branch = "impl/my-feature-M1"
        mock_wt.wt_type = "impl"
        mock_wt.path = tmp_path / "wt"

        mock_slot = MagicMock()
        mock_slot.slot_dir = str(tmp_path / "slot")
        mock_slot.slot_id = 1

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=[mock_wt],
            ),
            patch(
                "devops_ai.cli.done.check_dirty",
                return_value=MagicMock(is_dirty=False),
            ),
            patch(
                "devops_ai.cli.done.load_registry"
            ) as mock_lr,
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=mock_slot,
            ),
            patch("devops_ai.cli.done.stop_sandbox"),
            patch("devops_ai.cli.done.remove_slot_dir"),
            patch("devops_ai.cli.done.release_slot"),
            patch("devops_ai.cli.done.remove_worktree"),
            patch("devops_ai.cli.done.agent_deck") as mock_ad,
        ):
            mock_lr.return_value = MagicMock()
            (tmp_path / "slot").mkdir(exist_ok=True)

            code, msg = done_command(
                "my-feature-M1", repo_root=tmp_path
            )

        assert code == 0
        # Session title derived from branch: impl/my-feature-M1 → my-feature/M1
        mock_ad.remove_session.assert_called_once_with(
            "my-feature/M1"
        )

    def test_spec_branch_title(self, tmp_path: Path) -> None:
        """done derives spec/<feature> title from spec branch."""
        _setup_git_repo(tmp_path)
        _setup_infra_toml(tmp_path)

        mock_wt = MagicMock()
        mock_wt.feature = "my-feature"
        mock_wt.branch = "spec/my-feature"
        mock_wt.wt_type = "spec"
        mock_wt.path = tmp_path / "wt"

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=[mock_wt],
            ),
            patch(
                "devops_ai.cli.done.check_dirty",
                return_value=MagicMock(is_dirty=False),
            ),
            patch(
                "devops_ai.cli.done.load_registry"
            ) as mock_lr,
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=None,
            ),
            patch("devops_ai.cli.done.remove_worktree"),
            patch("devops_ai.cli.done.agent_deck") as mock_ad,
        ):
            mock_lr.return_value = MagicMock()
            mock_ad.is_available.return_value = True

            code, msg = done_command(
                "my-feature", repo_root=tmp_path
            )

        assert code == 0
        mock_ad.remove_session.assert_called_once_with(
            "spec/my-feature"
        )


class TestDoneNoAgentDeckSkips:
    def test_succeeds_without_agent_deck(
        self, tmp_path: Path
    ) -> None:
        """done succeeds when agent-deck not available."""
        _setup_git_repo(tmp_path)
        _setup_infra_toml(tmp_path)

        mock_wt = MagicMock()
        mock_wt.feature = "my-feature-M1"
        mock_wt.branch = "impl/my-feature-M1"
        mock_wt.wt_type = "impl"
        mock_wt.path = tmp_path / "wt"

        with (
            patch(
                "devops_ai.cli.done.list_worktrees",
                return_value=[mock_wt],
            ),
            patch(
                "devops_ai.cli.done.check_dirty",
                return_value=MagicMock(is_dirty=False),
            ),
            patch(
                "devops_ai.cli.done.load_registry"
            ) as mock_lr,
            patch(
                "devops_ai.cli.done.get_slot_for_worktree",
                return_value=None,
            ),
            patch("devops_ai.cli.done.remove_worktree"),
            patch("devops_ai.cli.done.agent_deck") as mock_ad,
        ):
            mock_lr.return_value = MagicMock()
            mock_ad.is_available.return_value = False

            code, msg = done_command(
                "my-feature-M1", repo_root=tmp_path
            )

        assert code == 0
        mock_ad.remove_session.assert_not_called()


class TestSessionWithSpec:
    def test_session_works_without_sandbox(
        self, tmp_path: Path
    ) -> None:
        """--session works for worktree-only (no sandbox)."""
        _setup_git_repo(tmp_path)
        _setup_milestone(tmp_path, "my-feature", "M1")
        # No infra.toml → no sandbox

        wt_path = (
            tmp_path.parent / f"{tmp_path.name}-impl-my-feature-M1"
        )

        with (
            patch(
                "devops_ai.cli.impl.create_impl_worktree",
                return_value=wt_path,
            ),
            patch(
                "devops_ai.cli.impl.agent_deck"
            ) as mock_ad,
        ):
            mock_ad.is_available.return_value = True

            code, msg = impl_command(
                "my-feature/M1",
                repo_root=tmp_path,
                session=True,
            )

        assert code == 0
        # Session should still be created even without sandbox
        mock_ad.add_session.assert_called_once()
        mock_ad.start_session.assert_called_once()
        mock_ad.send_to_session.assert_called_once()


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
