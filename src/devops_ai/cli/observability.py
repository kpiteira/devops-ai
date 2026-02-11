"""kinfra observability — Manage shared observability stack."""

from __future__ import annotations

import logging

from devops_ai.observability import (
    ObservabilityManager,
    ServiceState,
)
from devops_ai.registry import load_registry

logger = logging.getLogger(__name__)


def _up_command() -> tuple[int, str]:
    """Start the shared observability stack.

    Returns (exit_code, message).
    """
    try:
        mgr = ObservabilityManager()
        status = mgr.status()

        if all(s == ServiceState.RUNNING for s in status.services.values()):
            endpoints = mgr.get_endpoints()
            lines = ["Observability stack already running."]
            for name, url in sorted(endpoints.items()):
                lines.append(f"  {name}: {url}")
            return 0, "\n".join(lines)

        mgr.start()
        endpoints = mgr.get_endpoints()
        lines = ["Observability stack started."]
        for name, url in sorted(endpoints.items()):
            lines.append(f"  {name}: {url}")
        return 0, "\n".join(lines)
    except Exception as exc:
        return 1, f"Failed to start observability stack: {exc}"


def _down_command() -> tuple[int, str]:
    """Stop the shared observability stack.

    Returns (exit_code, message).
    """
    try:
        mgr = ObservabilityManager()
        mgr.stop()
    except Exception as exc:
        return 1, f"Failed to stop observability stack: {exc}"

    # Check for active sandboxes
    registry = load_registry()
    running = sum(
        1 for s in registry.slots.values() if s.status == "running"
    )

    lines = ["Observability stack stopped."]
    if running > 0:
        lines.append(
            f"  Note: {running} sandbox(es) still running "
            f"— their traces won't reach Jaeger."
        )
    return 0, "\n".join(lines)


def _status_command() -> tuple[int, str]:
    """Show observability stack status.

    Returns (exit_code, message).
    """
    try:
        mgr = ObservabilityManager()
        status = mgr.status()
    except Exception as exc:
        return 1, f"Failed to query observability status: {exc}"

    lines = ["Observability Stack:"]
    for svc_name in sorted(status.services):
        state = status.services[svc_name]
        endpoint = ""
        # Map service name to endpoint key
        ep_map = {
            "devops-ai-jaeger": "jaeger_ui",
            "devops-ai-grafana": "grafana",
            "devops-ai-prometheus": "prometheus",
        }
        ep_key = ep_map.get(svc_name, "")
        if ep_key and ep_key in status.endpoints:
            endpoint = f"  {status.endpoints[ep_key]}"
        lines.append(f"  {svc_name}: {state.value}{endpoint}")

    return 0, "\n".join(lines)
