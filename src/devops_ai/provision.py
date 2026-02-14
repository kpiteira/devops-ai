"""Provision module — secret resolution and file provisioning for sandboxes."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class SecretResolutionError(Exception):
    """Secret resolution failure with actionable guidance."""

    def __init__(self, var_name: str, ref: str, message: str) -> None:
        self.var_name = var_name
        self.ref = ref
        self.message = message
        super().__init__(message)


class FileProvisionError(Exception):
    """File provisioning failure with hint."""

    def __init__(self, dest: str, source: str, message: str) -> None:
        self.dest = dest
        self.source = source
        self.message = message
        super().__init__(message)


def resolve_secret(var_name: str, ref: str) -> str:
    """Resolve a single secret reference to its value.

    Raises SecretResolutionError with a user-actionable message.
    """
    if ref.startswith("op://"):
        return _resolve_op(var_name, ref)
    if ref.startswith("$"):
        return _resolve_env(var_name, ref)
    # Literal value
    return ref


def _resolve_env(var_name: str, ref: str) -> str:
    """Resolve a $VAR reference from host environment."""
    env_name = ref[1:]
    try:
        return os.environ[env_name]
    except KeyError:
        raise SecretResolutionError(
            var_name=var_name,
            ref=ref,
            message=(
                f"{var_name}: Environment variable {env_name} not set. "
                f"Export it or change to a different source in infra.toml."
            ),
        ) from None


def _resolve_op(var_name: str, ref: str) -> str:
    """Resolve an op:// reference via 1Password CLI."""
    if shutil.which("op") is None:
        raise SecretResolutionError(
            var_name=var_name,
            ref=ref,
            message=(
                f"{var_name}: 1Password CLI (op) not found. "
                f"Install: brew install 1password-cli "
                f"— or use $VAR references instead."
            ),
        )

    try:
        result = subprocess.run(
            ["op", "read", "--no-newline", ref],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise SecretResolutionError(
            var_name=var_name,
            ref=ref,
            message=f"{var_name}: 1Password CLI timed out. Try: eval $(op signin)",
        ) from None

    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "sign" in stderr or "auth" in stderr:
            raise SecretResolutionError(
                var_name=var_name,
                ref=ref,
                message=(
                    f"{var_name}: 1Password not authenticated. "
                    f"Run: eval $(op signin)"
                ),
            )
        raise SecretResolutionError(
            var_name=var_name,
            ref=ref,
            message=(
                f"{var_name}: Secret not found in 1Password: {ref}. "
                f"Check the reference in infra.toml."
            ),
        )

    return result.stdout


def resolve_all_secrets(
    secrets: dict[str, str],
) -> tuple[dict[str, str], list[SecretResolutionError]]:
    """Resolve all secrets. Returns (resolved_dict, errors).

    Attempts ALL — does not stop at first failure.
    """
    resolved: dict[str, str] = {}
    errors: list[SecretResolutionError] = []

    for var_name, ref in sorted(secrets.items()):
        try:
            resolved[var_name] = resolve_secret(var_name, ref)
        except SecretResolutionError as e:
            errors.append(e)

    return resolved, errors


def provision_files(
    files: dict[str, str],
    main_repo_root: Path,
    worktree_path: Path,
) -> tuple[list[str], list[FileProvisionError]]:
    """Copy config files from main repo to worktree.

    Returns (provisioned_file_names, errors).
    Attempts ALL — does not stop at first failure.
    """
    provisioned: list[str] = []
    errors: list[FileProvisionError] = []

    for dest_rel, source_rel in sorted(files.items()):
        source = (main_repo_root / source_rel).resolve()
        dest = (worktree_path / dest_rel).resolve()

        # Path traversal protection
        try:
            source.relative_to(main_repo_root.resolve())
        except ValueError:
            errors.append(
                FileProvisionError(
                    dest=dest_rel,
                    source=source_rel,
                    message=(
                        f"{dest_rel}: Source path escapes project root: "
                        f"{source_rel}"
                    ),
                )
            )
            continue
        try:
            dest.relative_to(worktree_path.resolve())
        except ValueError:
            errors.append(
                FileProvisionError(
                    dest=dest_rel,
                    source=source_rel,
                    message=(
                        f"{dest_rel}: Destination path escapes worktree: "
                        f"{dest_rel}"
                    ),
                )
            )
            continue

        if not source.is_file():
            hint = ""
            # Check for .example variant
            example = main_repo_root / f"{source_rel}.example"
            if example.is_file():
                hint = f" Hint: cp {source_rel}.example {source_rel}"
            errors.append(
                FileProvisionError(
                    dest=dest_rel,
                    source=source_rel,
                    message=(
                        f"{dest_rel}: Source not found at {source}.{hint}"
                    ),
                )
            )
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        provisioned.append(dest_rel)

    return provisioned, errors


def generate_secrets_file(
    resolved_secrets: dict[str, str],
    slot_dir: Path,
) -> Path:
    """Write .env.secrets to slot directory. Returns path.

    Raises ValueError if any key or value contains newlines or null bytes.
    """
    for key, value in resolved_secrets.items():
        for label, text in [("key", key), ("value", value)]:
            if "\n" in text or "\r" in text or "\0" in text:
                raise ValueError(
                    f"Secret {label} for '{key}' contains "
                    f"invalid characters (newline or null byte)"
                )
    lines = [
        f"{key}={value}" for key, value in sorted(resolved_secrets.items())
    ]
    path = slot_dir / ".env.secrets"
    path.write_text("\n".join(lines) + "\n")
    return path
