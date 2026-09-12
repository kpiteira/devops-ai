"""Tests for provisioning integration in impl command."""

from __future__ import annotations

from pathlib import Path

from devops_ai.cli.impl import _format_provision_failure
from devops_ai.provision import FileProvisionError, SecretResolutionError


class TestFormatProvisionFailure:
    def test_includes_sandbox_start_hint(self) -> None:
        errors = [
            SecretResolutionError(
                "TOKEN", "$TOKEN", "TOKEN: Environment variable TOKEN not set."
            ),
        ]
        wt_path = Path("/tmp/myproj-impl-feat-M1")
        result = _format_provision_failure(errors, wt_path)
        assert "kinfra sandbox start" in result
        assert str(wt_path) in result

    def test_includes_all_errors(self) -> None:
        errors = [
            SecretResolutionError(
                "A", "$A", "A: Environment variable A not set."
            ),
            SecretResolutionError(
                "B", "op://vault/item", "B: 1Password not authenticated."
            ),
            FileProvisionError(
                "config.yaml", "config.yaml", "config.yaml: Source not found."
            ),
        ]
        result = _format_provision_failure(errors, Path("/tmp/wt"))
        assert "A: Environment variable A not set" in result
        assert "B: 1Password not authenticated" in result
        assert "config.yaml: Source not found" in result

    def test_includes_provisioning_failed_header(self) -> None:
        errors = [
            SecretResolutionError("X", "$X", "X: not set"),
        ]
        result = _format_provision_failure(errors, Path("/tmp/wt"))
        assert "Provisioning failed" in result


class TestFreshSlotRefusesADirtyLabel:
    def test_unconfirmed_cleanup_stops_setup(self, tmp_path: Path) -> None:
        """A reused slot id whose label cannot be confirmed clean is refused."""
        from unittest.mock import patch

        from devops_ai.cli.impl import _setup_sandbox
        from devops_ai.config import InfraConfig
        from devops_ai.registry import Registry

        config = InfraConfig(
            project_name="myproj", prefix="myproj", has_sandbox=True,
            compose_file="docker-compose.yml",
        )
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        (tmp_path / "docker-compose.yml").write_text("services: {}")
        with (
            patch("devops_ai.cli.impl.load_registry",
                  return_value=Registry(version=1, slots={})),
            patch("devops_ai.cli.impl.clean_stale_entries"),
            patch("devops_ai.cli.impl.allocate_slot",
                  return_value=(2, {"API_PORT": 8082})),
            patch("devops_ai.cli.impl.slot_dir_path", return_value=slot_dir),
            patch("devops_ai.cli.impl.create_slot_dir", return_value=slot_dir),
            patch("devops_ai.cli.impl.copy_compose_to_slot",
                  return_value=slot_dir / "docker-compose.yml"),
            patch("devops_ai.cli.impl.claim_slot"),
            patch("devops_ai.cli.impl.force_cleanup_project",
                  return_value=False),
            patch("devops_ai.cli.impl.release_slot") as release,
            patch("devops_ai.cli.impl.remove_slot_dir") as rm_dir,
            patch("devops_ai.cli.impl.start_sandbox") as start,
        ):
            code, msg = _setup_sandbox(
                config, tmp_path, tmp_path / "wt", "feat", "M1"
            )
        assert code == 1
        assert "myproj-slot-2" in msg and "Could not confirm" in msg
        assert "kinfra done feat-M1" in msg
        release.assert_called_once()
        rm_dir.assert_called_once_with(slot_dir)
        start.assert_not_called()


class TestLosingClaimTouchesNothing:
    def test_no_slot_dir_writes_before_a_successful_claim(
        self, tmp_path: Path
    ) -> None:
        from unittest.mock import patch

        from devops_ai.cli.impl import _setup_sandbox
        from devops_ai.config import InfraConfig
        from devops_ai.registry import Registry, SlotClaimedError

        config = InfraConfig(
            project_name="myproj", prefix="myproj", has_sandbox=True,
            compose_file="docker-compose.yml",
        )
        (tmp_path / "docker-compose.yml").write_text("services: {}")
        with (
            patch("devops_ai.cli.impl.load_registry",
                  return_value=Registry(version=1, slots={})),
            patch("devops_ai.cli.impl.clean_stale_entries"),
            patch("devops_ai.cli.impl.allocate_slot",
                  return_value=(1, {"API_PORT": 8081})),
            patch("devops_ai.cli.impl.claim_slot",
                  side_effect=SlotClaimedError("Slot 1 was claimed")),
            patch("devops_ai.cli.impl.slot_dir_path",
                  return_value=tmp_path / "slot"),
            patch("devops_ai.cli.impl.create_slot_dir") as mkdir,
            patch("devops_ai.cli.impl.copy_compose_to_slot") as copy,
            patch("devops_ai.cli.impl.force_cleanup_project") as cleanup,
        ):
            code, msg = _setup_sandbox(
                config, tmp_path, tmp_path / "wt", "feat", "M1"
            )
        assert code == 1 and "claimed" in msg
        mkdir.assert_not_called()
        copy.assert_not_called()
        cleanup.assert_not_called()
