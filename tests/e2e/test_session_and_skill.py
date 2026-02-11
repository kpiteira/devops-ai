"""E2E test: agent-deck session integration and kworktree skill verification."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from devops_ai.agent_deck import is_available
from devops_ai.cli.done import done_command
from devops_ai.cli.impl import impl_command


def _agent_deck_sessions_json() -> list[dict]:
    """Get current agent-deck sessions as parsed JSON."""
    result = subprocess.run(
        ["agent-deck", "list", "-json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return json.loads(result.stdout)


def _agent_deck_remove(title: str) -> None:
    """Best-effort remove an agent-deck session by title."""
    subprocess.run(
        ["agent-deck", "remove", title],
        capture_output=True,
        text=True,
    )


@pytest.mark.e2e
class TestSessionIntegration:
    """Test --session flag against real agent-deck."""

    @pytest.fixture(autouse=True)
    def _check_agent_deck(self) -> None:
        is_available.cache_clear()
        if not is_available():
            pytest.skip("agent-deck not installed")

    def test_impl_session_creates_and_done_removes(
        self, e2e_project: dict
    ) -> None:
        """impl --session creates agent-deck session, done removes it."""
        repo_root: Path = e2e_project["repo_root"]
        feature = e2e_project["feature"]
        milestone = e2e_project["milestone"]
        title = f"{feature}/{milestone}"

        # Ensure no leftover session from previous run
        _agent_deck_remove(title)

        # ── Step 1: impl with --session ─────────────────────
        code, msg = impl_command(
            f"{feature}/{milestone}",
            repo_root=repo_root,
            session=True,
        )
        assert code == 0, f"impl_command failed: {msg}"
        assert "agent-deck session started" in msg.lower()

        # ── Step 2: Verify session exists in agent-deck ─────
        sessions = _agent_deck_sessions_json()
        titles = [s.get("title", "") for s in sessions]
        assert title in titles, (
            f"Session '{title}' not found in agent-deck. "
            f"Found: {titles}"
        )

        # ── Step 3: done cleans up session ──────────────────
        code, msg = done_command(
            f"{feature}-{milestone}",
            repo_root=repo_root,
            force=True,
        )
        assert code == 0, f"done_command failed: {msg}"

        # ── Step 4: Verify session removed ──────────────────
        sessions = _agent_deck_sessions_json()
        titles = [s.get("title", "") for s in sessions]
        assert title not in titles, (
            f"Session '{title}' still exists after done"
        )

    def test_impl_session_without_sandbox(
        self, e2e_project: dict
    ) -> None:
        """--session works even without sandbox config."""
        repo_root: Path = e2e_project["repo_root"]
        feature = e2e_project["feature"]
        milestone = e2e_project["milestone"]
        title = f"{feature}/{milestone}"

        # Remove infra.toml to disable sandbox
        infra_toml = repo_root / ".devops-ai" / "infra.toml"
        infra_backup = repo_root / ".devops-ai" / "infra.toml.bak"
        infra_toml.rename(infra_backup)

        # Ensure no leftover session
        _agent_deck_remove(title)

        try:
            code, msg = impl_command(
                f"{feature}/{milestone}",
                repo_root=repo_root,
                session=True,
            )
            assert code == 0, f"impl_command failed: {msg}"
            assert "agent-deck session started" in msg.lower()
            assert "no sandbox configured" in msg.lower()

            # Verify session exists
            sessions = _agent_deck_sessions_json()
            titles = [s.get("title", "") for s in sessions]
            assert title in titles
        finally:
            # Restore infra.toml and clean up
            infra_backup.rename(infra_toml)
            _agent_deck_remove(title)
            # Clean up worktree
            done_command(
                f"{feature}-{milestone}",
                repo_root=repo_root,
                force=True,
            )


@pytest.mark.e2e
class TestKworktreeSkill:
    """Verify kworktree skill file structure."""

    def _skill_path(self) -> Path:
        """Locate the skill file relative to repo root."""
        # Walk up from this test file to find repo root
        anchor = Path(__file__).resolve().parent
        for parent in (anchor, *anchor.parents):
            candidate = parent / "skills" / "kworktree" / "SKILL.md"
            if candidate.exists():
                return candidate
        pytest.fail("skills/kworktree/SKILL.md not found")

    def test_skill_exists(self) -> None:
        path = self._skill_path()
        assert path.exists()

    def test_all_commands_referenced(self) -> None:
        content = self._skill_path().read_text()
        for cmd in [
            "kinfra init",
            "kinfra spec",
            "kinfra impl",
            "kinfra done",
            "kinfra status",
            "kinfra worktrees",
        ]:
            assert cmd in content, f"Missing reference to '{cmd}'"

    def test_observability_referenced(self) -> None:
        content = self._skill_path().read_text()
        assert "observability" in content.lower()
        assert "46686" in content  # Jaeger UI port
        assert "43000" in content  # Grafana port

    def test_under_200_lines(self) -> None:
        lines = self._skill_path().read_text().splitlines()
        assert len(lines) < 200, f"Skill is {len(lines)} lines (max 200)"

    def test_sandbox_aware_coding_section(self) -> None:
        content = self._skill_path().read_text()
        assert "sandbox" in content.lower()
        assert "dynamic port" in content.lower() or "base_port" in content.lower()
