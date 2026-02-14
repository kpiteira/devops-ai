"""kinfra impl — Create an implementation worktree with optional sandbox."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from devops_ai import agent_deck
from devops_ai.config import InfraConfig, find_project_root, load_config
from devops_ai.observability import ObservabilityManager
from devops_ai.provision import (
    FileProvisionError,
    SecretResolutionError,
    generate_secrets_file,
    provision_files,
    resolve_all_secrets,
)
from devops_ai.registry import (
    SlotInfo,
    allocate_slot,
    claim_slot,
    clean_stale_entries,
    load_registry,
    release_slot,
    save_registry,
)
from devops_ai.sandbox import (
    copy_compose_to_slot,
    create_slot_dir,
    generate_env_file,
    generate_override,
    remove_slot_dir,
    run_health_gate,
    start_sandbox,
)
from devops_ai.worktree import (
    create_impl_worktree,
    impl_worktree_path,
    validate_feature_name,
)

logger = logging.getLogger(__name__)


def parse_feature_milestone(arg: str) -> tuple[str, str]:
    """Parse 'feature/milestone' argument.

    Raises ValueError if format is invalid.
    """
    if "/" not in arg:
        raise ValueError(
            f"Expected feature/milestone format, got: {arg!r}"
        )
    parts = arg.split("/", 1)
    return parts[0], parts[1]


def _find_milestone_file(
    repo_root: Path, feature: str, milestone: str
) -> Path | None:
    """Find milestone file matching the pattern."""
    impl_dir = (
        repo_root / "docs" / "designs" / feature / "implementation"
    )
    if not impl_dir.is_dir():
        return None
    matches = list(impl_dir.glob(f"{milestone}_*.md"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Prefer exact prefix match
        return matches[0]
    return None


def impl_command(
    arg: str,
    repo_root: Path | None = None,
    session: bool = False,
) -> tuple[int, str]:
    """Create an impl worktree with optional sandbox.

    Returns (exit_code, message).
    """
    if repo_root is None:
        repo_root = find_project_root() or Path.cwd()

    # Parse argument
    try:
        feature, milestone = parse_feature_milestone(arg)
    except ValueError as e:
        return 1, str(e)

    try:
        validate_feature_name(feature)
    except ValueError as e:
        return 1, f"Invalid feature name: {e}"

    # Load config (optional)
    config = (
        load_config(repo_root)
        if (repo_root / ".devops-ai").is_dir()
        else None
    )
    prefix = config.prefix if config else repo_root.name

    # Find milestone file
    ms_file = _find_milestone_file(repo_root, feature, milestone)
    if ms_file is None:
        return 1, (
            f"No milestone file found matching "
            f"'{milestone}_*.md' in "
            f"docs/designs/{feature}/implementation/"
        )

    # Check worktree doesn't already exist
    wt_path = impl_worktree_path(repo_root, prefix, feature, milestone)
    if wt_path.exists():
        return 1, f"Worktree already exists at {wt_path}"

    # Create worktree
    try:
        wt_path = create_impl_worktree(
            repo_root, prefix, feature, milestone
        )
    except Exception as e:
        return 1, f"Error creating worktree: {e}"

    # If no sandbox config, we're done (but session may still apply)
    if not config or not config.has_sandbox:
        msg = (
            f"Created worktree: {wt_path}\n"
            f"  Branch: impl/{feature}-{milestone}\n"
            f"  No sandbox configured."
        )
        if session:
            session_msg = _setup_session(
                feature, milestone, wt_path
            )
            if session_msg:
                msg += f"\n{session_msg}"
        return 0, msg

    # Observability: network is required (sandbox override declares it
    # external), full stack is non-fatal.
    obs_mgr = ObservabilityManager()
    try:
        obs_mgr.ensure_network()
    except Exception as exc:
        return 1, (
            f"Cannot create observability network: {exc}\n"
            f"  Worktree created at {wt_path}"
        )
    try:
        obs_mgr.ensure_running()
    except Exception:
        logger.warning(
            "Could not start observability stack — continuing without it"
        )

    # --- Sandbox setup ---
    return _setup_sandbox(
        config, repo_root, wt_path, feature, milestone, session
    )


def _format_provision_failure(
    errors: list[SecretResolutionError | FileProvisionError],
    wt_path: Path,
) -> str:
    """Format provisioning errors with actionable recovery instructions."""
    lines = [
        f"Created worktree: {wt_path}",
        "",
        "\u2717 Provisioning failed:",
        "",
    ]
    for err in errors:
        lines.append(f"  {err.message}")
        lines.append("")

    lines.append("Sandbox not started. After fixing, run:")
    lines.append(f"  cd {wt_path} && kinfra sandbox start")
    return "\n".join(lines)


def _setup_session(
    feature: str,
    milestone: str,
    wt_path: Path,
) -> str:
    """Set up agent-deck session. Returns status message."""
    if not agent_deck.is_available():
        return "  agent-deck not found, skipping session management"
    title = f"{feature}/{milestone}"
    agent_deck.add_session(
        title, group="dev", path=str(wt_path)
    )
    agent_deck.start_session(title)
    agent_deck.send_to_session(
        title, f"/kbuild {feature}/{milestone}", delay=3
    )
    return f"  agent-deck session started: {title}"


def _setup_sandbox(
    config: InfraConfig,
    repo_root: Path,
    wt_path: Path,
    feature: str,
    milestone: str,
    session: bool = False,
) -> tuple[int, str]:
    """Set up sandbox for an impl worktree."""
    registry = load_registry()
    clean_stale_entries(registry)

    # Allocate slot
    try:
        slot_id, ports = allocate_slot(registry, config)
    except RuntimeError as e:
        return 1, f"Slot allocation failed: {e}"

    # Create slot dir
    slot_dir = create_slot_dir(config.project_name, slot_id)

    # Claim slot
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    compose_path = repo_root / config.compose_file
    compose_copy = copy_compose_to_slot(compose_path, slot_dir)

    slot_info = SlotInfo(
        slot_id=slot_id,
        project=config.project_name,
        worktree_path=str(wt_path),
        slot_dir=str(slot_dir),
        compose_file_copy=str(compose_copy),
        ports=ports,
        claimed_at=now,
        status="provisioning",
    )
    claim_slot(registry, slot_info)

    # Generate files
    generate_env_file(config, slot_info, slot_dir)
    generate_override(config, slot_info, wt_path, repo_root, slot_dir)

    # Provision files and resolve secrets
    file_errors: list[FileProvisionError] = []
    provisioned_files: list[str] = []
    if config.files:
        provisioned_files, file_errors = provision_files(
            config.files, repo_root, wt_path
        )

    secret_errors: list[SecretResolutionError] = []
    resolved_secrets: dict[str, str] = {}
    if config.secrets:
        resolved_secrets, secret_errors = resolve_all_secrets(config.secrets)

    all_errors: list[SecretResolutionError | FileProvisionError] = (
        file_errors + secret_errors  # type: ignore[operator]
    )
    if all_errors:
        # Keep slot allocated so `kinfra sandbox start` can retry
        return 1, _format_provision_failure(all_errors, wt_path)

    if resolved_secrets:
        generate_secrets_file(resolved_secrets, slot_dir)

    # Start sandbox
    try:
        start_sandbox(config, slot_info, wt_path)
    except RuntimeError as e:
        # Cleanup: release slot, remove slot dir, keep worktree
        release_slot(registry, slot_id)
        remove_slot_dir(slot_dir)
        return 1, (
            f"Sandbox failed to start: {e}\n"
            f"  Worktree preserved at {wt_path}"
        )

    # Mark slot as running now that containers are up
    slot_info.status = "running"
    save_registry(registry)

    # Health gate
    healthy = run_health_gate(config, slot_info)

    # Build report
    lines = [
        f"Created worktree: {wt_path}",
        f"  Branch: impl/{feature}-{milestone}",
        f"  Slot: {slot_id}",
    ]
    for env_var, port in sorted(ports.items()):
        lines.append(f"  {env_var}: {port}")

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

    if session:
        session_msg = _setup_session(feature, milestone, wt_path)
        if session_msg:
            lines.append(session_msg)

    return 0, "\n".join(lines)
