"""Tests for provision module — secret resolution and file provisioning."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from devops_ai.provision import (
    SecretResolutionError,
    generate_secrets_file,
    provision_files,
    resolve_all_secrets,
    resolve_secret,
)

# --- Secret resolution ---


class TestResolveSecretLiteral:
    def test_literal_returns_as_is(self) -> None:
        assert resolve_secret("DB_PASSWORD", "localdev") == "localdev"

    def test_empty_literal(self) -> None:
        assert resolve_secret("EMPTY", "") == ""


class TestResolveSecretEnvVar:
    def test_reads_from_environment(self) -> None:
        with patch.dict(os.environ, {"MY_TOKEN": "secret-val"}):
            assert resolve_secret("MY_TOKEN", "$MY_TOKEN") == "secret-val"

    def test_raises_when_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SecretResolutionError, match="not set"):
                resolve_secret("MISSING_VAR", "$MISSING_VAR")

    def test_error_includes_var_name(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SecretResolutionError) as exc_info:
                resolve_secret("MY_TOKEN", "$MY_TOKEN")
            assert exc_info.value.var_name == "MY_TOKEN"
            assert exc_info.value.ref == "$MY_TOKEN"


class TestResolveSecretOnePassword:
    def test_op_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            with pytest.raises(
                SecretResolutionError, match="1Password CLI.*not found"
            ):
                resolve_secret("TOKEN", "op://vault/item/field")

    def test_op_success(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/local/bin/op"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "resolved-secret"
            result = resolve_secret("TOKEN", "op://vault/item/field")
            assert result == "resolved-secret"
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["op", "read", "--no-newline", "op://vault/item/field"]

    def test_op_not_authenticated(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/local/bin/op"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "not signed in"
            with pytest.raises(
                SecretResolutionError, match="not authenticated"
            ):
                resolve_secret("TOKEN", "op://vault/item/field")

    def test_op_item_not_found(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/local/bin/op"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "could not find item"
            with pytest.raises(
                SecretResolutionError, match="not found"
            ):
                resolve_secret("TOKEN", "op://vault/item/field")


class TestResolveAllSecrets:
    def test_collects_all_errors(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            resolved, errors = resolve_all_secrets({
                "A": "$A_VAR",
                "B": "$B_VAR",
                "C": "literal-ok",
            })
            assert "C" in resolved
            assert resolved["C"] == "literal-ok"
            assert len(errors) == 2
            var_names = {e.var_name for e in errors}
            assert var_names == {"A", "B"}

    def test_all_succeed(self) -> None:
        with patch.dict(os.environ, {"TOKEN": "val"}):
            resolved, errors = resolve_all_secrets({
                "TOKEN": "$TOKEN",
                "DB_PASS": "localdev",
            })
            assert len(errors) == 0
            assert resolved == {"TOKEN": "val", "DB_PASS": "localdev"}

    def test_empty_secrets(self) -> None:
        resolved, errors = resolve_all_secrets({})
        assert resolved == {}
        assert errors == []


# --- File provisioning ---


class TestProvisionFiles:
    def test_copies_file(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        (main_repo / "config.yaml").write_text("setting: value")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        provisioned, errors = provision_files(
            {"config.yaml": "config.yaml"}, main_repo, worktree
        )
        assert errors == []
        assert "config.yaml" in provisioned
        assert (worktree / "config.yaml").read_text() == "setting: value"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        (main_repo / "certs").mkdir()
        (main_repo / "certs" / "dev.pem").write_text("cert-data")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        provisioned, errors = provision_files(
            {"certs/dev.pem": "certs/dev.pem"}, main_repo, worktree
        )
        assert errors == []
        assert (worktree / "certs" / "dev.pem").read_text() == "cert-data"

    def test_error_when_source_missing(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        provisioned, errors = provision_files(
            {"config.yaml": "config.yaml"}, main_repo, worktree
        )
        assert len(errors) == 1
        assert errors[0].dest == "config.yaml"

    def test_error_hints_example_file(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        (main_repo / "config.yaml.example").write_text("example")
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        _, errors = provision_files(
            {"config.yaml": "config.yaml"}, main_repo, worktree
        )
        assert len(errors) == 1
        assert "config.yaml.example" in errors[0].message

    def test_collects_all_errors(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        _, errors = provision_files(
            {"a.yaml": "a.yaml", "b.yaml": "b.yaml"},
            main_repo,
            worktree,
        )
        assert len(errors) == 2

    def test_different_source_and_dest(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        (main_repo / ".env.example").write_text("KEY=val")
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        provisioned, errors = provision_files(
            {".env": ".env.example"}, main_repo, worktree
        )
        assert errors == []
        assert (worktree / ".env").read_text() == "KEY=val"


# --- Secrets file generation ---


class TestGenerateSecretsFile:
    def test_writes_key_value_format(self, tmp_path: Path) -> None:
        path = generate_secrets_file(
            {"TOKEN": "secret-val", "API_KEY": "sk-123"},
            tmp_path,
        )
        assert path == tmp_path / ".env.secrets"
        content = path.read_text()
        assert "API_KEY=sk-123\n" in content
        assert "TOKEN=secret-val\n" in content

    def test_empty_secrets(self, tmp_path: Path) -> None:
        path = generate_secrets_file({}, tmp_path)
        assert path.read_text() == "\n"

    def test_rejects_newline_in_value(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            generate_secrets_file({"KEY": "val\nEVIL=injected"}, tmp_path)

    def test_rejects_carriage_return_in_value(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            generate_secrets_file({"KEY": "val\rEVIL"}, tmp_path)

    def test_rejects_null_byte_in_key(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            generate_secrets_file({"KEY\0EVIL": "val"}, tmp_path)


class TestProvisionFilesPathTraversal:
    def test_source_path_traversal_blocked(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        _, errors = provision_files(
            {"config.yaml": "../../../etc/passwd"}, main_repo, worktree
        )
        assert len(errors) == 1
        assert "escapes project root" in errors[0].message

    def test_dest_path_traversal_blocked(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        (main_repo / "config.yaml").write_text("data")
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        _, errors = provision_files(
            {"../evil.yaml": "config.yaml"}, main_repo, worktree
        )
        assert len(errors) == 1
        assert "escapes worktree" in errors[0].message
