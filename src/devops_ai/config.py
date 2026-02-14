"""Config loader for .devops-ai/infra.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MountEntry:
    """A parsed Docker-style mount specification (host:container[:ro])."""

    host: str
    container: str
    readonly: bool = False


@dataclass
class ServicePort:
    """A port mapping: env var name to base port number."""

    env_var: str
    base_port: int


@dataclass
class InfraConfig:
    """Typed representation of .devops-ai/infra.toml."""

    project_name: str
    prefix: str
    has_sandbox: bool = False
    compose_file: str = "docker-compose.yml"
    ports: list[ServicePort] = field(default_factory=list)
    health_endpoint: str | None = None
    health_port_var: str | None = None
    health_timeout: int = 60
    code_mounts: list[MountEntry] = field(default_factory=list)
    code_mount_targets: list[str] = field(default_factory=list)
    shared_mounts: list[MountEntry] = field(default_factory=list)
    shared_mount_targets: list[str] = field(default_factory=list)
    otel_endpoint_var: str = "OTEL_EXPORTER_OTLP_ENDPOINT"
    otel_namespace_var: str = "OTEL_RESOURCE_ATTRIBUTES"
    env: dict[str, str] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)


def parse_mount(spec: str) -> MountEntry:
    """Parse a Docker-style mount string: host:container[:ro]."""
    parts = spec.split(":")
    if len(parts) == 3:
        if parts[2] != "ro":
            raise ValueError(
                f"Invalid mount syntax: {spec!r} (expected host:container[:ro])"
            )
        return MountEntry(host=parts[0], container=parts[1], readonly=True)
    if len(parts) == 2:
        return MountEntry(host=parts[0], container=parts[1])
    raise ValueError(f"Invalid mount syntax: {spec!r} (expected host:container[:ro])")


def load_config(project_root: Path) -> InfraConfig | None:
    """Load and parse .devops-ai/infra.toml from the given project root.

    Returns None if infra.toml does not exist.
    Raises ValueError if required fields are missing.
    """
    config_path = project_root / ".devops-ai" / "infra.toml"
    if not config_path.exists():
        return None

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    name = project.get("name")
    if not name:
        raise ValueError("Missing required field: [project].name in infra.toml")

    prefix = project.get("prefix", name)

    sandbox = data.get("sandbox")
    if sandbox is None:
        return InfraConfig(project_name=name, prefix=prefix, has_sandbox=False)

    compose_file = sandbox.get("compose_file", "docker-compose.yml")

    # Ports
    ports_data = sandbox.get("ports", {})
    ports = [ServicePort(env_var=k, base_port=v) for k, v in ports_data.items()]

    # Health
    health = sandbox.get("health", {})
    health_endpoint = health.get("endpoint")
    health_port_var = health.get("port_var")
    health_timeout = health.get("timeout", 60)

    # Mounts
    mounts = sandbox.get("mounts", {})
    code_mounts = [parse_mount(m) for m in mounts.get("code", [])]
    code_mount_targets = mounts.get("code_targets", [])
    shared_mounts = [parse_mount(m) for m in mounts.get("shared", [])]
    shared_mount_targets = mounts.get("shared_targets", [])

    # OTEL overrides
    otel = sandbox.get("otel", {})
    otel_endpoint_var = otel.get(
        "endpoint_var", "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_namespace_var = otel.get(
        "namespace_var", "OTEL_RESOURCE_ATTRIBUTES"
    )

    # Provisioning sections
    env = sandbox.get("env", {})
    secrets = sandbox.get("secrets", {})
    files = sandbox.get("files", {})

    return InfraConfig(
        project_name=name,
        prefix=prefix,
        has_sandbox=True,
        compose_file=compose_file,
        ports=ports,
        health_endpoint=health_endpoint,
        health_port_var=health_port_var,
        health_timeout=health_timeout,
        code_mounts=code_mounts,
        code_mount_targets=code_mount_targets,
        shared_mounts=shared_mounts,
        shared_mount_targets=shared_mount_targets,
        otel_endpoint_var=otel_endpoint_var,
        otel_namespace_var=otel_namespace_var,
        env=env,
        secrets=secrets,
        files=files,
    )


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from start (default: cwd) looking for .devops-ai/ directory.

    Returns the directory containing .devops-ai/, or None if not found
    within 10 levels.
    """
    current = (start or Path.cwd()).resolve()
    for _ in range(10):
        if (current / ".devops-ai").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
