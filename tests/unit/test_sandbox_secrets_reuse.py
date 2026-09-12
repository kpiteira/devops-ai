"""kinfra sandbox start/rebuild reuse materialised secrets (pilot 2026-09-08)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from devops_ai.cli.sandbox_cmd import (
    SecretsPlan,
    plan_secrets,
    sandbox_start_command,
)


class TestPlanSecrets:
    def test_no_secrets_configured(self, tmp_path: Path) -> None:
        assert plan_secrets({}, tmp_path, refresh=False) == SecretsPlan.NONE

    def test_resolve_when_nothing_materialised(self, tmp_path: Path) -> None:
        plan = plan_secrets({"T": "op://v/i/f"}, tmp_path, refresh=False)
        assert plan == SecretsPlan.RESOLVE

    def test_reuse_when_materialised(self, tmp_path: Path) -> None:
        (tmp_path / ".env.secrets").write_text("T=redacted\n")
        plan = plan_secrets({"T": "op://v/i/f"}, tmp_path, refresh=False)
        assert plan == SecretsPlan.REUSE

    def test_refresh_forces_resolution(self, tmp_path: Path) -> None:
        (tmp_path / ".env.secrets").write_text("T=redacted\n")
        plan = plan_secrets({"T": "op://v/i/f"}, tmp_path, refresh=True)
        assert plan == SecretsPlan.RESOLVE


def _worktree_with_slot(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A git repo with infra.toml declaring one op:// secret, and its slot."""
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    (wt / ".devops-ai").mkdir()
    (wt / ".devops-ai" / "infra.toml").write_text(
        '[project]\nname = "myproj"\n\n[sandbox]\n'
        'compose_file = "docker-compose.yml"\n\n[sandbox.ports]\n'
        "API_PORT = 8080\n\n[sandbox.secrets]\nT = \"op://v/i/f\"\n"
    )
    slot_dir = tmp_path / "slots" / "myproj-1"
    slot_dir.mkdir(parents=True)
    (slot_dir / ".env.sandbox").write_text("COMPOSE_PROJECT_NAME=myproj-slot-1\n")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"slots": {"1": {
        "slot_id": 1, "project": "myproj", "worktree_path": str(wt),
        "slot_dir": str(slot_dir),
        "compose_file_copy": str(slot_dir / "docker-compose.yml"),
        "ports": {"API_PORT": 8081}, "claimed_at": "2025-01-01T00:00:00",
        "status": "stopped",
    }}}))
    return wt, slot_dir, registry


class TestStartCommandReusesMaterialisedSecrets:
    """The command path: reuse skips the resolver; --refresh-secrets runs it."""

    def _run(self, wt: Path, registry: Path, *, refresh: bool):
        with (
            patch("devops_ai.cli.sandbox_cmd.REGISTRY_PATH", registry),
            patch("devops_ai.cli.sandbox_cmd.resolve_all_secrets",
                  return_value=({"T": "x"}, [])) as resolve,
            patch("devops_ai.cli.sandbox_cmd.generate_secrets_file"),
            patch("devops_ai.cli.sandbox_cmd.start_sandbox"),
            patch("devops_ai.cli.sandbox_cmd.run_health_gate",
                  return_value=True),
            patch("devops_ai.cli.sandbox_cmd.save_registry"),
        ):
            code, msg = sandbox_start_command(
                worktree_path=wt, refresh_secrets=refresh
            )
        return code, msg, resolve

    def test_reuse_skips_resolution(self, tmp_path: Path) -> None:
        wt, slot_dir, registry = _worktree_with_slot(tmp_path)
        (slot_dir / ".env.secrets").write_text("T=materialised\n")
        code, msg, resolve = self._run(wt, registry, refresh=False)
        assert code == 0, msg
        resolve.assert_not_called()
        assert "reused" in msg and "--refresh-secrets" in msg

    def test_refresh_resolves(self, tmp_path: Path) -> None:
        wt, slot_dir, registry = _worktree_with_slot(tmp_path)
        (slot_dir / ".env.secrets").write_text("T=materialised\n")
        code, msg, resolve = self._run(wt, registry, refresh=True)
        assert code == 0, msg
        resolve.assert_called_once()
        assert "Resolved secrets" in msg

    def test_nothing_materialised_resolves(self, tmp_path: Path) -> None:
        wt, _slot_dir, registry = _worktree_with_slot(tmp_path)
        code, msg, resolve = self._run(wt, registry, refresh=False)
        assert code == 0, msg
        resolve.assert_called_once()
