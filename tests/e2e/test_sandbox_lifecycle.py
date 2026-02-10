"""E2E test: full sandbox lifecycle — impl -> verify -> status -> done -> cleanup."""

from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from devops_ai.cli.done import done_command
from devops_ai.cli.impl import impl_command
from devops_ai.cli.status import status_command
from devops_ai.registry import load_registry


@pytest.mark.e2e
class TestSandboxLifecycle:
    """Full lifecycle: impl creates sandbox, status shows it, done tears it down."""

    def test_full_lifecycle(self, e2e_project: dict) -> None:  # noqa: C901
        repo_root: Path = e2e_project["repo_root"]
        worktree_path: Path = e2e_project["worktree_path"]
        project_name: str = e2e_project["project_name"]
        expected_port: int = e2e_project["expected_port"]

        # ── Step 1: kinfra impl ──────────────────────────────────
        code, msg = impl_command(
            "e2e-feat/M1", repo_root=repo_root
        )
        assert code == 0, f"impl_command failed: {msg}"
        assert worktree_path.exists(), "Worktree not created"

        # ── Step 2: Verify Docker container on offset port ───────
        deadline = time.monotonic() + 60
        reachable = False
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{expected_port}", timeout=3
                ) as resp:
                    if resp.status == 200:
                        reachable = True
                        break
            except Exception:
                time.sleep(2)

        assert reachable, (
            f"Service not responding on port {expected_port}"
        )

        # ── Step 3: Verify slot artifacts ────────────────────────
        slots_base = Path.home() / ".devops-ai" / "slots"
        slot_dirs = list(slots_base.glob(f"{project_name}-*"))
        assert len(slot_dirs) == 1, f"Expected 1 slot dir, got {slot_dirs}"

        slot_dir = slot_dirs[0]
        assert (slot_dir / ".env.sandbox").exists()
        assert (slot_dir / "docker-compose.override.yml").exists()
        assert (slot_dir / "docker-compose.yml").exists()

        # ── Step 4: Verify registry entry ────────────────────────
        registry = load_registry()
        e2e_slots = [
            s
            for s in registry.slots.values()
            if s.project == project_name
        ]
        assert len(e2e_slots) == 1
        slot = e2e_slots[0]
        assert slot.ports["APP_PORT"] == expected_port

        # ── Step 5: kinfra status ────────────────────────────────
        code, msg = status_command(cwd=worktree_path)
        assert code == 0
        assert project_name in msg
        assert str(expected_port) in msg

        # ── Step 6: kinfra done ──────────────────────────────────
        code, msg = done_command(
            "e2e-feat-M1", repo_root=repo_root, force=True
        )
        assert code == 0, f"done_command failed: {msg}"

        # ── Step 7: Verify full cleanup ──────────────────────────
        # Worktree removed
        assert not worktree_path.exists(), "Worktree still exists"

        # Slot dir removed
        remaining = list(slots_base.glob(f"{project_name}-*"))
        assert len(remaining) == 0, f"Slot dirs remain: {remaining}"

        # Registry clean
        registry = load_registry()
        leftover = [
            s
            for s in registry.slots.values()
            if s.project == project_name
        ]
        assert len(leftover) == 0, f"Registry entries remain: {leftover}"

        # No Docker containers
        result = subprocess.run(
            [
                "docker", "ps", "-a",
                "--filter", f"name={project_name}-slot",
                "--format", "{{.Names}}",
            ],
            capture_output=True,
            text=True,
        )
        assert not result.stdout.strip(), (
            f"Containers still running: {result.stdout}"
        )
