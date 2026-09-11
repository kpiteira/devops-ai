"""kinfra impl --session --group passes an explicit agent-deck group (2026-09-06)."""

from __future__ import annotations

from pathlib import Path

from devops_ai import agent_deck
from devops_ai.cli.impl import _setup_session


class TestSessionGroup:
    def test_group_is_passed_explicitly(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        calls: list[dict[str, str]] = []
        monkeypatch.setattr(agent_deck, "is_available", lambda: True)
        monkeypatch.setattr(
            agent_deck, "add_session",
            lambda title, *, group, path: calls.append(
                {"title": title, "group": group, "path": path}
            ),
        )
        monkeypatch.setattr(agent_deck, "start_session", lambda title: None)
        monkeypatch.setattr(
            agent_deck, "send_to_session",
            lambda title, message, delay=3: None,
        )
        _setup_session("feat", "M2", tmp_path, group="khealth")
        assert calls == [
            {"title": "feat/M2", "group": "khealth", "path": str(tmp_path)}
        ]

    def test_default_group_is_dev(self, tmp_path: Path, monkeypatch) -> None:
        seen: list[str] = []
        monkeypatch.setattr(agent_deck, "is_available", lambda: True)
        monkeypatch.setattr(
            agent_deck, "add_session",
            lambda title, *, group, path: seen.append(group),
        )
        monkeypatch.setattr(agent_deck, "start_session", lambda title: None)
        monkeypatch.setattr(
            agent_deck, "send_to_session",
            lambda title, message, delay=3: None,
        )
        _setup_session("feat", "M1", tmp_path)
        assert seen == ["dev"]
