"""kinfra sandbox start/rebuild reuse materialised secrets (pilot 2026-09-08)."""

from __future__ import annotations

from pathlib import Path

from devops_ai.cli.sandbox_cmd import SecretsPlan, plan_secrets


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
