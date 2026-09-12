"""kinfra sandbox — start/stop/rebuild sandbox for existing worktrees."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from devops_ai.config import find_project_root, load_config
from devops_ai.provision import (
    FileProvisionError,
    SecretResolutionError,
    describe_secret_source,
    generate_secrets_file,
    provision_files,
    resolve_all_secrets,
    secure_secrets_file,
)
from devops_ai.registry import (
    DEFAULT_REGISTRY_PATH,
    get_slot_for_worktree,
    load_registry,
    update_slot_status,
)
from devops_ai.sandbox import (
    copy_compose_to_slot,
    run_health_gate,
    start_sandbox,
)
from devops_ai.worktree import main_repo_root

logger = logging.getLogger(__name__)

REGISTRY_PATH = DEFAULT_REGISTRY_PATH


class SecretsPlan(Enum):
    """What a sandbox start does about secrets."""

    NONE = "none"        # no [sandbox.secrets] configured
    REUSE = "reuse"      # materialised .env.secrets present, not refreshing
    RESOLVE = "resolve"  # resolve references (may prompt a keychain)


def _materialised_names(secrets_file: Path) -> set[str] | None:
    """Variable names in a materialised env file, or None if unreadable.

    Names only — never values.
    """
    try:
        text = secrets_file.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    names: set[str] = set()
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            names.add(line.split("=", 1)[0].strip())
    return names


def plan_secrets(
    secrets: dict[str, str], slot_dir: Path, *, refresh: bool
) -> SecretsPlan:
    """Decide whether to reuse the slot's materialised secrets.

    Default is reuse when the file exists and its variable names are exactly
    the configured ones: the running containers already use it, and
    re-resolving can park an unattended session on a human's keychain (v2
    pilot, 2026-09-08). A name added or removed in infra.toml, an unreadable
    file, or ``refresh`` forces resolution; an empty configuration removes a
    leftover file.
    """
    materialised = slot_dir / ".env.secrets"
    if not secrets:
        # Nothing configured: a leftover file must not reach compose.
        materialised.unlink(missing_ok=True)
        return SecretsPlan.NONE
    if refresh or not materialised.exists():
        return SecretsPlan.RESOLVE
    names = _materialised_names(materialised)
    if names is None or names != set(secrets):
        # Unreadable, or the configured set changed (a name added or
        # removed) — re-resolve. A changed *reference* under an unchanged
        # name is invisible here; that is what --refresh-secrets is for.
        return SecretsPlan.RESOLVE
    return SecretsPlan.REUSE


def _sandbox_up(
    worktree_path: Path | None = None,
    *,
    build: bool = False,
    refresh_secrets: bool = False,
) -> tuple[int, str]:
    """Shared logic for sandbox start and rebuild.

    Re-runs file provisioning before starting containers; secrets are
    re-resolved only when nothing is materialised or ``refresh_secrets`` is
    set. If ``build`` is True, rebuilds images from source.
    """
    cwd = (worktree_path or Path.cwd()).resolve()
    verb = "rebuilt" if build else "started"
    retry_cmd = "kinfra sandbox rebuild" if build else "kinfra sandbox start"
    if refresh_secrets:
        retry_cmd += " --refresh-secrets"

    # Walk up to find the worktree root (registered path)
    wt_path = cwd
    registry = load_registry(REGISTRY_PATH)
    slot_info = get_slot_for_worktree(registry, wt_path)
    if slot_info is None:
        # Try parent directories (user may be in a subdirectory)
        candidate = wt_path.parent
        while candidate != candidate.parent:
            slot_info = get_slot_for_worktree(registry, candidate)
            if slot_info is not None:
                wt_path = candidate
                break
            candidate = candidate.parent
    if slot_info is None:
        return 1, (
            "Not a kinfra worktree, or sandbox not allocated.\n"
            "  Use 'kinfra impl <feature/milestone>' to create a sandbox."
        )

    # Load config from worktree
    config_root = find_project_root(wt_path)
    if config_root is None:
        return 1, "No .devops-ai/ directory found in worktree."

    config = load_config(config_root)
    if config is None:
        return 1, "No infra.toml found in .devops-ai/."

    # Find main repo root for file provisioning
    main_repo = main_repo_root(wt_path)
    if main_repo is None:
        return 1, "Cannot determine main repository root."

    slot_dir = Path(slot_info.slot_dir)

    # Provision files
    file_errors: list[FileProvisionError] = []
    provisioned_files: list[str] = []
    if config.files:
        provisioned_files, file_errors = provision_files(
            config.files, main_repo, wt_path
        )

    # Resolve secrets — or reuse what the slot already has
    secret_errors: list[SecretResolutionError] = []
    resolved_secrets: dict[str, str] = {}
    secrets_plan = plan_secrets(
        config.secrets, slot_dir, refresh=refresh_secrets
    )
    if secrets_plan is SecretsPlan.RESOLVE:
        resolved_secrets, secret_errors = resolve_all_secrets(
            config.secrets, main_repo
        )
    elif secrets_plan is SecretsPlan.REUSE:
        # Before compose reads it, not after the sandbox is up: a file written
        # before the mode was enforced would otherwise stay world-readable for
        # the whole of startup — and for good, if startup fails.
        secure_secrets_file(slot_dir)

    all_errors: list[SecretResolutionError | FileProvisionError] = (
        file_errors + secret_errors  # type: ignore[operator]
    )
    if all_errors:
        lines = ["\u2717 Provisioning failed:", ""]
        for err in all_errors:
            lines.append(f"  {err.message}")
            lines.append("")
        lines.append(f"Fix the issues above and retry: {retry_cmd}")
        return 1, "\n".join(lines)

    # Write secrets file
    if resolved_secrets:
        generate_secrets_file(resolved_secrets, slot_dir)

    # Refresh the slot's compose copy: teardown runs `down` from the copy,
    # and a rebuild may have added services or volumes since `impl`.
    compose_src = wt_path / config.compose_file
    if compose_src.exists():
        copy_compose_to_slot(compose_src, slot_dir)

    # Start sandbox
    try:
        start_sandbox(config, slot_info, wt_path, build=build)
    except RuntimeError as e:
        return 1, f"Sandbox failed to {verb}: {e}"

    # Mark slot as running (locked; never rewrites other entries)
    update_slot_status(
        registry, slot_info.slot_id, "running", REGISTRY_PATH
    )

    # Health gate
    healthy = run_health_gate(config, slot_info)

    # Report
    lines = [
        f"Sandbox {verb} for: {wt_path}",
        f"  Slot: {slot_info.slot_id}",
    ]

    if provisioned_files:
        lines.append("Provisioned files:")
        for fname in provisioned_files:
            source = config.files.get(fname, fname)
            lines.append(f"  {fname} \u2190 {source} \u2713")

    if resolved_secrets:
        lines.append("Resolved secrets:")
        for var_name in sorted(resolved_secrets.keys()):
            source = describe_secret_source(config.secrets.get(var_name, ""))
            lines.append(f"  {var_name} \u2190 {source} \u2713")
    elif secrets_plan is SecretsPlan.REUSE:
        lines.append(
            "Secrets: reused the slot's materialised .env.secrets "
            "(--refresh-secrets to re-resolve)"
        )

    if not healthy:
        lines.append(
            f"  Warning: Health check timed out after "
            f"{config.health_timeout}s"
        )

    return 0, "\n".join(lines)


def sandbox_start_command(
    worktree_path: Path | None = None,
    *,
    refresh_secrets: bool = False,
) -> tuple[int, str]:
    """Start sandbox for an existing worktree. Returns (exit_code, message)."""
    return _sandbox_up(
        worktree_path, build=False, refresh_secrets=refresh_secrets
    )


def sandbox_rebuild_command(
    worktree_path: Path | None = None,
    *,
    refresh_secrets: bool = False,
) -> tuple[int, str]:
    """Rebuild sandbox for an existing worktree. Returns (exit_code, message).

    Like start, but rebuilds Docker images from source code.
    """
    return _sandbox_up(
        worktree_path, build=True, refresh_secrets=refresh_secrets
    )
