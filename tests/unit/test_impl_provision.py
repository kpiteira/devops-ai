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
