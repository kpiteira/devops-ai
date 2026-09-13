"""Provision module — secret resolution and file provisioning for sandboxes.

Secret resolution itself lives in `devops_ai.secrets`, shared with the `ksecret`
CLI: kinfra resolves through the same providers, so every scheme a provider adds
reaches `[sandbox.secrets]` with no wiring here. This module keeps kinfra's side
of it — the main-repo base directory, and the slot's secrets file.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Mapping
from pathlib import Path

from devops_ai.secrets import (
    ResolveContext,
    SecretResolutionError,
    layered_env,
    provider_for,
    resolve,
    resolve_all,
)

logger = logging.getLogger(__name__)

SECRETS_FILE_NAME = ".env.secrets"
SECRETS_FILE_MODE = 0o600

__all__ = [
    "FileProvisionError",
    "describe_secret_source",
    "secure_secrets_file",
    "SecretResolutionError",
    "generate_secrets_file",
    "provision_files",
    "resolve_all_secrets",
    "resolve_secret",
]


class FileProvisionError(Exception):
    """File provisioning failure with hint."""

    def __init__(self, dest: str, source: str, message: str) -> None:
        self.dest = dest
        self.source = source
        self.message = message
        super().__init__(message)


def secure_secrets_file(slot_dir: Path) -> Path | None:
    """Tighten an existing .env.secrets to owner-only. Returns it, or None.

    The reuse path (`plan_secrets` -> REUSE) hands an already-materialised file
    straight to compose without regenerating it, so a file written before the
    mode was enforced would keep its old permissions for the life of the slot.
    The invariant is that this file *is* 0600, not that it is 0600 when freshly
    written.
    """
    path = slot_dir / SECRETS_FILE_NAME
    if not path.is_file():
        return None
    path.chmod(SECRETS_FILE_MODE)
    return path


def describe_secret_source(ref: str) -> str:
    """A display-safe description of where a secret comes from.

    A reference names a provider and is safe to show; a literal is its own
    value, so it is never echoed. Which is which comes from the providers, not
    from a list of schemes here, so every scheme a provider claims — today's and
    the ones M2 and M3 add — is shown rather than mistaken for a literal.
    """
    return ref if provider_for(ref) is not None else "(literal, not shown)"


def resolve_secret(var_name: str, ref: str, base_dir: Path | None = None) -> str:
    """Resolve a single secret reference to its value.

    `base_dir` is the main repository root: gitignored files live there, not in
    the worktree. Raises SecretResolutionError with a user-actionable message.
    """
    return resolve(var_name, ref, _context(base_dir))


def resolve_all_secrets(
    secrets: dict[str, str],
    base_dir: Path | None = None,
) -> tuple[dict[str, str], list[SecretResolutionError]]:
    """Resolve all secrets. Returns (resolved_dict, errors).

    Attempts ALL — does not stop at first failure.
    """
    ordered = {name: secrets[name] for name in sorted(secrets)}
    return resolve_all(ordered, _context(base_dir, ordered))


def _context(
    base_dir: Path | None, siblings: Mapping[str, str] | None = None
) -> ResolveContext:
    """The environment `[sandbox.secrets]` resolves in.

    Literal entries are laid over the process environment before any reference
    is resolved, so a declared `OP_ACCOUNT` reaches the 1Password process a
    sibling reference spawns — the same ordering `ksecret run` gives an env
    file, which is what the brief means by kinfra using the same resolver.
    Sorting makes this order-independent: the two passes, not the key order,
    decide what a provider sees.
    """
    env = layered_env(siblings or {})
    if base_dir is None:
        return ResolveContext(env=env)
    return ResolveContext(base_dir=base_dir, env=env)


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
    """Write .env.secrets to slot directory, mode 0600. Returns path.

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
    path = slot_dir / SECRETS_FILE_NAME
    path.touch(mode=SECRETS_FILE_MODE, exist_ok=True)
    path.chmod(SECRETS_FILE_MODE)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
