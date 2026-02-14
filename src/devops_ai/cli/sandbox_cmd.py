"""kinfra sandbox — start/stop sandbox for existing worktrees."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from devops_ai.config import find_project_root, load_config
from devops_ai.provision import (
    FileProvisionError,
    SecretResolutionError,
    generate_secrets_file,
    provision_files,
    resolve_all_secrets,
)
from devops_ai.registry import (
    DEFAULT_REGISTRY_PATH,
    get_slot_for_worktree,
    load_registry,
)
from devops_ai.sandbox import run_health_gate, start_sandbox

logger = logging.getLogger(__name__)

REGISTRY_PATH = DEFAULT_REGISTRY_PATH


def _find_main_repo_root(worktree_path: Path) -> Path | None:
    """Find the main repo root from a worktree via git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=worktree_path,
        )
        if result.returncode == 0 and result.stdout.strip():
            # --git-common-dir returns the .git dir of the main worktree
            git_dir = Path(result.stdout.strip())
            return git_dir.parent
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def sandbox_start_command(
    worktree_path: Path | None = None,
) -> tuple[int, str]:
    """Start sandbox for an existing worktree. Returns (exit_code, message).

    Re-runs provisioning (files + secrets) before starting containers.
    """
    wt_path = (worktree_path or Path.cwd()).resolve()

    # Find slot from registry
    registry = load_registry(REGISTRY_PATH)
    slot_info = get_slot_for_worktree(registry, wt_path)
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
    main_repo = _find_main_repo_root(wt_path)
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

    # Resolve secrets
    secret_errors: list[SecretResolutionError] = []
    resolved_secrets: dict[str, str] = {}
    if config.secrets:
        resolved_secrets, secret_errors = resolve_all_secrets(config.secrets)

    all_errors: list[SecretResolutionError | FileProvisionError] = (
        file_errors + secret_errors  # type: ignore[operator]
    )
    if all_errors:
        lines = ["\u2717 Provisioning failed:", ""]
        for err in all_errors:
            lines.append(f"  {err.message}")
            lines.append("")
        lines.append("Fix the issues above and retry: kinfra sandbox start")
        return 1, "\n".join(lines)

    # Write secrets file
    if resolved_secrets:
        generate_secrets_file(resolved_secrets, slot_dir)

    # Start sandbox
    try:
        start_sandbox(config, slot_info, wt_path)
    except RuntimeError as e:
        return 1, f"Sandbox failed to start: {e}"

    # Health gate
    healthy = run_health_gate(config, slot_info)

    # Report
    lines = [
        f"Sandbox started for: {wt_path}",
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
            ref = config.secrets.get(var_name, "")
            lines.append(f"  {var_name} \u2190 {ref} \u2713")

    if not healthy:
        lines.append(
            f"  Warning: Health check timed out after "
            f"{config.health_timeout}s"
        )

    return 0, "\n".join(lines)
