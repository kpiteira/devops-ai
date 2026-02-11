"""Observability Manager — shared Jaeger + Grafana + Prometheus stack."""

from __future__ import annotations

import enum
import json
import logging
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path.home() / ".devops-ai" / "observability"

NETWORK_NAME = "devops-ai-observability"

ENDPOINTS = {
    "jaeger_ui": "http://localhost:46686",
    "jaeger_otlp": "http://localhost:44317",
    "grafana": "http://localhost:43000",
    "prometheus": "http://localhost:49090",
}

_EXPECTED_SERVICES = {
    "devops-ai-jaeger",
    "devops-ai-grafana",
    "devops-ai-prometheus",
}


def _find_template() -> Path:
    """Locate the observability compose template.

    Walks up from this file to find the repo root ``templates/`` directory.
    Works for editable installs (``uv run``, ``pip install -e .``).
    """
    anchor = Path(__file__).resolve().parent
    for parent in (anchor, *anchor.parents):
        candidate = parent / "templates" / "observability" / "docker-compose.yml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Cannot locate templates/observability/docker-compose.yml"
    )


class ServiceState(enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    NOT_FOUND = "not_found"


@dataclass
class ObservabilityStatus:
    services: dict[str, ServiceState] = field(default_factory=dict)
    endpoints: dict[str, str] = field(default_factory=dict)


class ObservabilityManager:
    """Manages the shared observability stack lifecycle."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or DEFAULT_BASE_DIR
        self._compose_file = self._base_dir / "docker-compose.yml"

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def ensure_network(self) -> None:
        """Create the Docker network if it doesn't exist (idempotent).

        Raises RuntimeError if the network cannot be created.
        """
        try:
            result = subprocess.run(
                ["docker", "network", "inspect", NETWORK_NAME],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Docker is not installed or not on PATH"
            ) from None
        if result.returncode != 0:
            logger.info("Creating Docker network %s", NETWORK_NAME)
            create = subprocess.run(
                ["docker", "network", "create", NETWORK_NAME],
                capture_output=True,
                text=True,
            )
            if create.returncode != 0:
                raise RuntimeError(
                    f"Failed to create network {NETWORK_NAME}: "
                    f"{create.stderr.strip()}"
                )

    # ------------------------------------------------------------------
    # Compose file
    # ------------------------------------------------------------------

    def ensure_compose_file(self) -> None:
        """Copy template to base dir if not already present."""
        if self._compose_file.exists():
            return
        self._base_dir.mkdir(parents=True, exist_ok=True)
        template = _find_template()
        shutil.copy2(template, self._compose_file)
        logger.info("Copied observability template to %s", self._compose_file)

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the observability stack (network + compose up).

        Raises RuntimeError if compose up fails.
        """
        self.ensure_network()
        self.ensure_compose_file()

        cmd = [
            "docker", "compose",
            "-f", str(self._compose_file),
            "up", "-d",
        ]
        logger.info("Starting observability stack: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(
                "Docker is not installed or not on PATH"
            ) from None
        if result.returncode != 0:
            raise RuntimeError(
                f"Observability stack failed to start: "
                f"{result.stderr.strip()}"
            )

        self._wait_for_jaeger()

    def stop(self) -> None:
        """Stop the observability stack. Does NOT remove the network."""
        cmd = [
            "docker", "compose",
            "-f", str(self._compose_file),
            "down",
        ]
        logger.info("Stopping observability stack")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(
                "Docker is not installed or not on PATH"
            ) from None
        if result.returncode != 0:
            logger.warning(
                "Observability stack stop returned non-zero: %s",
                result.stderr.strip(),
            )

    def _wait_for_jaeger(self, timeout: int = 30) -> None:
        """Poll Jaeger UI until reachable or timeout."""
        url = ENDPOINTS["jaeger_ui"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as resp:
                    if resp.status == 200:
                        logger.info("Jaeger UI reachable")
                        return
            except Exception:
                # Jaeger may not be up yet; retry until timeout.
                pass
            time.sleep(1)
        logger.warning("Jaeger UI not reachable after %ds", timeout)

    # ------------------------------------------------------------------
    # Status / ensure_running
    # ------------------------------------------------------------------

    def ensure_running(self) -> None:
        """Start the stack if not all services are running (idempotent)."""
        st = self.status()
        if all(s == ServiceState.RUNNING for s in st.services.values()):
            logger.info("Observability stack already running")
            return
        self.start()

    def status(self) -> ObservabilityStatus:
        """Query per-service state."""
        self.ensure_compose_file()
        cmd = [
            "docker", "compose",
            "-f", str(self._compose_file),
            "ps", "--format", "json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        services: dict[str, ServiceState] = {}

        if result.returncode == 0 and result.stdout.strip():
            # docker compose ps --format json outputs NDJSON (one object
            # per line) or a JSON array depending on version.
            raw = result.stdout.strip()
            if raw.startswith("["):
                entries = json.loads(raw)
            else:
                entries = [
                    json.loads(line)
                    for line in raw.splitlines()
                    if line.strip()
                ]
            for entry in entries:
                name = entry.get("Service", "")
                state = entry.get("State", "")
                if state == "running":
                    services[name] = ServiceState.RUNNING
                else:
                    services[name] = ServiceState.STOPPED

        # Mark missing services as NOT_FOUND
        for svc in _EXPECTED_SERVICES:
            if svc not in services:
                services[svc] = ServiceState.NOT_FOUND

        return ObservabilityStatus(
            services=services,
            endpoints=dict(ENDPOINTS),
        )

    def get_endpoints(self) -> dict[str, str]:
        """Return endpoint URLs for the observability services."""
        return dict(ENDPOINTS)
