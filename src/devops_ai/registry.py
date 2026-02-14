"""Global slot registry — tracks claimed slots across all projects.

Persists to ~/.devops-ai/registry.json. File locking via fcntl.flock()
prevents concurrent corruption from multiple terminals.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from devops_ai.config import InfraConfig
from devops_ai.ports import check_ports_available, compute_ports

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = Path.home() / ".devops-ai" / "registry.json"


@dataclass
class SlotInfo:
    """Information about a claimed slot."""

    slot_id: int
    project: str
    worktree_path: str
    slot_dir: str
    compose_file_copy: str
    ports: dict[str, int]
    claimed_at: str
    status: str  # "running" | "stopped"


@dataclass
class Registry:
    """Global slot registry."""

    version: int = 1
    slots: dict[int, SlotInfo] = field(default_factory=dict)


def load_registry(path: Path | None = None) -> Registry:
    """Load registry from JSON. Creates empty registry if file doesn't exist."""
    path = path or DEFAULT_REGISTRY_PATH
    if not path.exists():
        return Registry()

    try:
        text = path.read_text()
        if not text.strip():
            return Registry()
        data = json.loads(text)
    except (json.JSONDecodeError, OSError):
        logger.warning("Registry file corrupt, starting fresh: %s", path)
        return Registry()

    version = data.get("version", 1)
    slots: dict[int, SlotInfo] = {}
    for key, val in data.get("slots", {}).items():
        slot_id = int(key)
        slots[slot_id] = SlotInfo(
            slot_id=val["slot_id"],
            project=val["project"],
            worktree_path=val["worktree_path"],
            slot_dir=val["slot_dir"],
            compose_file_copy=val.get("compose_file_copy", ""),
            ports=val.get("ports", {}),
            claimed_at=val.get("claimed_at", ""),
            status=val.get("status", "running"),
        )
    return Registry(version=version, slots=slots)


def save_registry(registry: Registry, path: Path | None = None) -> None:
    """Write registry to JSON atomically.

    Writes to a temp file in the same directory, then renames. This
    prevents partial reads from seeing truncated JSON.
    """
    path = path or DEFAULT_REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": registry.version,
        "slots": {str(k): asdict(v) for k, v in registry.slots.items()},
    }

    # Write to temp file, then atomic rename
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.replace(tmp_path, path)
    except BaseException:
        # Clean up temp file on any error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def allocate_slot(
    registry: Registry, config: InfraConfig
) -> tuple[int, dict[str, int]]:
    """Find next free slot with TCP bind test.

    Returns (slot_id, ports_dict). Raises RuntimeError if all exhausted.
    """
    for slot_id in range(1, 101):
        if slot_id in registry.slots:
            continue
        ports = compute_ports(config, slot_id)
        conflicts = check_ports_available(ports)
        if conflicts:
            for c in conflicts:
                logger.info(
                    "Slot %d skipped: port %d (%s) in use", slot_id, c.port, c.env_var
                )
            continue
        return slot_id, ports
    raise RuntimeError(
        "No slots available (1-100 all claimed or have port conflicts)"
    )


def claim_slot(
    registry: Registry, slot_info: SlotInfo, path: Path | None = None
) -> None:
    """Add a slot to the registry and persist."""
    registry.slots[slot_info.slot_id] = slot_info
    save_registry(registry, path)


def release_slot(
    registry: Registry, slot_id: int, path: Path | None = None
) -> None:
    """Remove a slot from the registry and persist."""
    registry.slots.pop(slot_id, None)
    save_registry(registry, path)


def get_slot_for_worktree(
    registry: Registry, worktree_path: Path
) -> SlotInfo | None:
    """Look up a slot by its worktree path."""
    path_str = str(worktree_path)
    for slot in registry.slots.values():
        if slot.worktree_path == path_str:
            return slot
    return None


def clean_stale_entries(registry: Registry) -> list[int]:
    """Remove entries where worktree or slot dir no longer exists.

    Returns list of removed slot IDs.
    """
    stale: list[int] = []
    for slot_id, info in list(registry.slots.items()):
        wt_exists = Path(info.worktree_path).exists()
        sd_exists = Path(info.slot_dir).exists()
        if not wt_exists or not sd_exists:
            reason = []
            if not wt_exists:
                reason.append("worktree missing")
            if not sd_exists:
                reason.append("slot dir missing")
            logger.warning(
                "Removing stale slot %d (%s): %s",
                slot_id,
                info.project,
                ", ".join(reason),
            )
            stale.append(slot_id)
    for slot_id in stale:
        del registry.slots[slot_id]
    return stale
