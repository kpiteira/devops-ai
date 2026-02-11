"""Port allocator — offset computation and conflict detection."""

from __future__ import annotations

import socket
from dataclasses import dataclass

from devops_ai.config import InfraConfig


@dataclass
class PortConflict:
    """A port that failed the TCP bind availability check."""

    env_var: str
    port: int
    message: str


def compute_ports(config: InfraConfig, slot_id: int) -> dict[str, int]:
    """Compute actual ports for a slot: base_port + slot_id for each declared port."""
    return {sp.env_var: sp.base_port + slot_id for sp in config.ports}


def check_ports_available(ports: dict[str, int]) -> list[PortConflict]:
    """Attempt TCP bind on each port; return list of conflicts.

    Uses SO_REUSEADDR and binds to 127.0.0.1. Ports that cannot be bound
    are reported as conflicts.
    """
    conflicts: list[PortConflict] = []
    for env_var, port in ports.items():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
        except OSError as e:
            conflicts.append(PortConflict(env_var=env_var, port=port, message=str(e)))
    return conflicts


def check_base_port_safety(
    config: InfraConfig,
    other_entries: list[dict[str, object]],
) -> list[str]:
    """Warn if this project's base ports are within 100 of another project's.

    other_entries: list of dicts with "project" (str) and "ports" (dict[str, int])
    keys — extracted from the registry's claimed slots.

    Returns advisory warning strings (not blocking).
    """
    warnings: list[str] = []
    my_base_ports = {sp.env_var: sp.base_port for sp in config.ports}

    for entry in other_entries:
        other_project = str(entry["project"])
        if other_project == config.project_name:
            continue
        other_ports = entry.get("ports", {})
        if not isinstance(other_ports, dict):
            continue
        for other_var, other_base in other_ports.items():
            if not isinstance(other_base, int):
                continue
            for my_var, my_base in my_base_ports.items():
                distance = abs(my_base - other_base)
                if distance < 100:
                    warnings.append(
                        f"Port proximity warning: {config.project_name}:{my_var} "
                        f"(base {my_base}) is within {distance} of "
                        f"{other_project}:{other_var} (base {other_base})"
                    )
    return warnings
