"""Tests for kinfra sandbox start command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from devops_ai.cli.sandbox_cmd import sandbox_start_command


def _setup_registry(tmp_path: Path, worktree_path: str, slot_id: int = 1) -> Path:
    """Create a registry.json with one slot entry."""
    registry_dir = tmp_path / "devops-ai"
    registry_dir.mkdir(parents=True)
    registry_path = registry_dir / "registry.json"

    slot_dir = tmp_path / "slots" / f"myproj-{slot_id}"
    slot_dir.mkdir(parents=True)
    (slot_dir / ".env.sandbox").write_text("COMPOSE_PROJECT_NAME=myproj-slot-1\n")

    entry = {
        "slot_id": slot_id,
        "project": "myproj",
        "worktree_path": worktree_path,
        "slot_dir": str(slot_dir),
        "compose_file_copy": str(slot_dir / "docker-compose.yml"),
        "ports": {"API_PORT": 8081},
        "claimed_at": "2025-01-01T00:00:00",
        "status": "stopped",
    }
    registry_path.write_text(json.dumps({"slots": {str(slot_id): entry}}))
    return registry_path


class TestSandboxStartNotWorktree:
    def test_errors_when_no_slot_found(self, tmp_path: Path) -> None:
        registry_path = _setup_registry(tmp_path, "/some/other/path")
        with patch("devops_ai.cli.sandbox_cmd.REGISTRY_PATH", registry_path):
            code, msg = sandbox_start_command(worktree_path=tmp_path / "unknown")
        assert code == 1
        assert "not a kinfra worktree" in msg.lower() or "not allocated" in msg.lower()
