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

    def test_new_secret_in_config_forces_resolution(self, tmp_path: Path) -> None:
        """A secret added since materialisation must not be silently absent."""
        (tmp_path / ".env.secrets").write_text("T=redacted\n")
        plan = plan_secrets(
            {"T": "op://v/i/f", "U": "op://v/i/g"}, tmp_path, refresh=False
        )
        assert plan == SecretsPlan.RESOLVE

    def test_removed_secret_forces_resolution(self, tmp_path: Path) -> None:
        """A name dropped from config must not keep being injected."""
        (tmp_path / ".env.secrets").write_text("T=redacted\nU=redacted\n")
        plan = plan_secrets({"T": "op://v/i/f"}, tmp_path, refresh=False)
        assert plan == SecretsPlan.RESOLVE

    def test_empty_config_drops_leftover_file(self, tmp_path: Path) -> None:
        (tmp_path / ".env.secrets").write_text("T=redacted\n")
        assert plan_secrets({}, tmp_path, refresh=False) == SecretsPlan.NONE
        assert not (tmp_path / ".env.secrets").exists()

    def test_unreadable_file_forces_resolution(self, tmp_path: Path) -> None:
        (tmp_path / ".env.secrets").write_bytes(b"\xff\xfe\x00garbage")
        plan = plan_secrets({"T": "op://v/i/f"}, tmp_path, refresh=False)
        assert plan == SecretsPlan.RESOLVE

    def test_refresh_forces_resolution(self, tmp_path: Path) -> None:
        (tmp_path / ".env.secrets").write_text("T=redacted\n")
        plan = plan_secrets({"T": "op://v/i/f"}, tmp_path, refresh=True)
        assert plan == SecretsPlan.RESOLVE

