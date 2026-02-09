"""kinfra init — project inspection and config generation."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import typer
from ruamel.yaml import YAML

from devops_ai.config import find_project_root

# Image patterns that identify observability services
OBSERVABILITY_PATTERNS = [
    re.compile(r"^jaegertracing/"),
    re.compile(r"^prom/prometheus"),
    re.compile(r"^grafana/grafana"),
]


def detect_services_from_compose(
    yaml_content: str,
) -> dict[str, dict[str, Any]]:
    """Parse compose YAML and extract services with ports and images.

    Returns dict of service_name -> {image, ports: [{host, container}]}.
    """
    yml = YAML()
    data = yml.load(yaml_content)
    if not data or "services" not in data:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for name, svc in data["services"].items():
        ports = []
        for port_spec in svc.get("ports", []):
            parsed = _parse_port_spec(str(port_spec))
            if parsed:
                ports.append(parsed)

        result[name] = {
            "image": svc.get("image"),
            "ports": ports,
        }
    return result


def _parse_port_spec(spec: str) -> dict[str, int] | None:
    """Parse a Docker port spec like '8080:8080' into host/container."""
    # Handle "HOST:CONTAINER" format
    spec = spec.strip('"').strip("'")
    # Skip already-parameterized ports like ${VAR:-8080}:8080
    if "${" in spec:
        return None
    parts = spec.split(":")
    if len(parts) == 2:
        try:
            return {
                "host": int(parts[0]),
                "container": int(parts[1]),
            }
        except ValueError:
            return None
    return None


def identify_observability_services(
    services: dict[str, dict[str, Any]],
) -> list[str]:
    """Identify observability services by image name."""
    obs_names = []
    for name, svc in services.items():
        image = svc.get("image") or ""
        for pattern in OBSERVABILITY_PATTERNS:
            if pattern.search(image):
                obs_names.append(name)
                break
    return obs_names


def detect_project_name(project_root: Path) -> str:
    """Detect project name from multiple sources."""
    # 1. .devops-ai/project.md
    project_md = project_root / ".devops-ai" / "project.md"
    if project_md.exists():
        content = project_md.read_text()
        match = re.search(r"\*\*Name:\*\*\s*(.+)", content)
        if match:
            return match.group(1).strip()

    # 2. pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        name: str | None = data.get("project", {}).get("name")
        if name:
            return name

    # 3. package.json
    pkg_json = project_root / "package.json"
    if pkg_json.exists():
        pkg_data = json.loads(pkg_json.read_text())
        pkg_name: str | None = pkg_data.get("name")
        if pkg_name:
            return pkg_name

    # 4. Fallback to directory name
    return project_root.name


def find_compose_files(project_root: Path) -> list[Path]:
    """Find compose files in the project root."""
    patterns = ["docker-compose*.yml", "compose*.yml"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(project_root.glob(pattern))
    return sorted(set(files))


def generate_infra_toml(
    project_name: str,
    prefix: str,
    compose_file: str,
    ports: dict[str, int],
    health_endpoint: str | None = None,
    health_port_var: str | None = None,
    health_timeout: int = 60,
    code_mounts: list[str] | None = None,
    code_mount_targets: list[str] | None = None,
    shared_mounts: list[str] | None = None,
    shared_mount_targets: list[str] | None = None,
) -> str:
    """Generate infra.toml content as a string."""
    lines = [
        "[project]",
        f'name = "{project_name}"',
        f'prefix = "{prefix}"',
        "",
        "[sandbox]",
        f'compose_file = "{compose_file}"',
    ]

    if health_endpoint:
        lines.append("")
        lines.append("[sandbox.health]")
        lines.append(f'endpoint = "{health_endpoint}"')
        if health_port_var:
            lines.append(f'port_var = "{health_port_var}"')
        if health_timeout != 60:
            lines.append(f"timeout = {health_timeout}")

    if ports:
        lines.append("")
        lines.append("[sandbox.ports]")
        for var, port in ports.items():
            lines.append(f"{var} = {port}")

    if code_mounts or shared_mounts:
        lines.append("")
        lines.append("[sandbox.mounts]")
        if code_mounts:
            items = ", ".join(f'"{m}"' for m in code_mounts)
            lines.append(f"code = [{items}]")
        if code_mount_targets:
            items = ", ".join(f'"{t}"' for t in code_mount_targets)
            lines.append(f"code_targets = [{items}]")
        if shared_mounts:
            items = ", ".join(f'"{m}"' for m in shared_mounts)
            lines.append(f"shared = [{items}]")
        if shared_mount_targets:
            items = ", ".join(
                f'"{t}"' for t in shared_mount_targets
            )
            lines.append(f"shared_targets = [{items}]")

    lines.append("")
    return "\n".join(lines)


def check_existing_config(
    project_root: Path,
) -> tuple[bool, str | None]:
    """Check if infra.toml already exists. Returns (exists, project_name)."""
    config_path = project_root / ".devops-ai" / "infra.toml"
    if not config_path.exists():
        return False, None
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    name = data.get("project", {}).get("name")
    return True, name


def check_docker_running() -> bool:
    """Check if Docker is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def init_command(project_root: Path | None = None) -> int:
    """Run the interactive init flow. Returns exit code."""
    if project_root is None:
        project_root = find_project_root() or Path.cwd()

    # Check for existing config
    exists, existing_name = check_existing_config(project_root)
    if exists:
        typer.echo(
            f"Found existing config for '{existing_name}'."
        )
        if not typer.confirm("Update existing config?", default=False):
            typer.echo("Aborted.")
            return 0

    # Check Docker
    if not check_docker_running():
        typer.echo(
            "Warning: Docker not running. "
            "Init can proceed, but sandbox features need Docker."
        )

    # Find compose files
    compose_files = find_compose_files(project_root)
    if not compose_files:
        typer.echo("No docker-compose.yml or compose.yml found.")
        compose_file = typer.prompt(
            "Compose file path", default="docker-compose.yml"
        )
    elif len(compose_files) == 1:
        compose_file = compose_files[0].name
        typer.echo(f"Found compose file: {compose_file}")
    else:
        names = ", ".join(f.name for f in compose_files)
        typer.echo(f"Found compose files: {names}")
        compose_file = typer.prompt(
            "Which compose file?", default=compose_files[0].name
        )

    # Parse services
    compose_path = project_root / compose_file
    services: dict[str, dict[str, Any]] = {}
    if compose_path.exists():
        services = detect_services_from_compose(
            compose_path.read_text()
        )

    # Identify observability services
    obs_services = identify_observability_services(services)
    app_services = {
        k: v for k, v in services.items() if k not in obs_services
    }

    if services:
        typer.echo(f"\nDetected {len(services)} services:")
        for name, svc in services.items():
            ports_str = ", ".join(
                str(p["host"]) for p in svc["ports"]
            )
            label = " (observability)" if name in obs_services else ""
            typer.echo(f"  {name}: ports [{ports_str}]{label}")

    if obs_services:
        typer.echo(
            f"\nObservability services ({', '.join(obs_services)}) "
            "will be provided by kinfra's shared stack."
        )

    # Detect project name
    detected_name = detect_project_name(project_root)
    project_name = typer.prompt(
        "Project name", default=detected_name
    )
    prefix = typer.prompt("Worktree prefix", default=project_name)

    # Health endpoint
    health_endpoint = typer.prompt(
        "Health check endpoint (empty to skip)",
        default="/api/v1/health",
    )
    if not health_endpoint:
        health_endpoint = None

    # Build port map for app services
    ports: dict[str, int] = {}
    health_port_var: str | None = None
    for svc_name, svc in app_services.items():
        for port_info in svc["ports"]:
            var_name = (
                f"{prefix.upper().replace('-', '_')}"
                f"_{svc_name.upper().replace('-', '_')}_PORT"
            )
            ports[var_name] = port_info["host"]
            if health_port_var is None and health_endpoint:
                health_port_var = var_name

    # Generate and write config
    toml_content = generate_infra_toml(
        project_name=project_name,
        prefix=prefix,
        compose_file=compose_file,
        ports=ports,
        health_endpoint=health_endpoint,
        health_port_var=health_port_var,
    )

    config_dir = project_root / ".devops-ai"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "infra.toml").write_text(toml_content)

    typer.echo("\nConfig written to .devops-ai/infra.toml")
    return 0
