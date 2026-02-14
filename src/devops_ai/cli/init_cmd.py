"""kinfra init — project inspection and config generation."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
from ruamel.yaml import YAML

from devops_ai.compose import rewrite_compose
from devops_ai.config import find_project_root

# Image patterns that identify observability services
OBSERVABILITY_PATTERNS = [
    re.compile(r"^jaegertracing/"),
    re.compile(r"^prom/prometheus"),
    re.compile(r"^grafana/grafana"),
]


@dataclass
class EnvVarCandidate:
    """An undeclared env var found in compose."""

    name: str
    services: list[str]
    default: str | None = None


@dataclass
class FileMountCandidate:
    """A gitignored bind mount found in compose."""

    host_path: str
    container_path: str
    service: str
    source_exists: bool = False
    example_exists: bool = False
    example_path: str | None = None


@dataclass
class InitPlan:
    """Structured result of project detection — no prompts, no file writes."""

    project_root: Path
    project_name: str
    prefix: str
    compose_file: str
    compose_path: Path
    services: dict[str, dict[str, Any]]
    obs_services: list[str]
    app_services: dict[str, dict[str, Any]]
    ports: dict[str, int]
    health_endpoint: str | None
    health_port_var: str | None
    toml_content: str = ""
    env_var_candidates: list[EnvVarCandidate] = field(default_factory=list)
    file_mount_candidates: list[FileMountCandidate] = field(
        default_factory=list
    )


def detect_project(project_root: Path) -> InitPlan:
    """Run the full detection pipeline and return a structured plan.

    Pure function — no prompts, no file writes.
    """
    # Find compose files
    compose_files = find_compose_files(project_root)
    compose_file = compose_files[0].name if compose_files else "docker-compose.yml"
    compose_path = project_root / compose_file

    # Parse services
    services: dict[str, dict[str, Any]] = {}
    if compose_path.exists():
        services = detect_services_from_compose(compose_path.read_text())

    # Identify obs vs app services
    obs_services = identify_observability_services(services)
    app_services = {k: v for k, v in services.items() if k not in obs_services}

    # Detect project name
    project_name = detect_project_name(project_root)
    prefix = project_name

    # Default health endpoint
    health_endpoint: str | None = "/api/v1/health"
    health_port_var: str | None = None

    # Build port map from app services
    ports: dict[str, int] = {}
    for svc_name, svc in app_services.items():
        for port_info in svc["ports"]:
            var_name = (
                f"{prefix.upper().replace('-', '_')}"
                f"_{svc_name.upper().replace('-', '_')}_PORT"
            )
            ports[var_name] = port_info["host"]
            if health_port_var is None and health_endpoint:
                health_port_var = var_name

    # Detect env vars and gitignored mounts
    env_var_candidates: list[EnvVarCandidate] = []
    file_mount_candidates: list[FileMountCandidate] = []
    if compose_path.exists():
        compose_text = compose_path.read_text()
        known_vars = (
            set(ports.keys())
            | {"COMPOSE_PROJECT_NAME"}
            | {"OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_RESOURCE_ATTRIBUTES"}
        )
        env_var_candidates = detect_env_vars(compose_text, known_vars)
        file_mount_candidates = detect_gitignored_mounts(
            compose_text, project_root
        )

    # Generate toml content
    toml_content = generate_infra_toml(
        project_name=project_name,
        prefix=prefix,
        compose_file=compose_file,
        ports=ports,
        health_endpoint=health_endpoint,
        health_port_var=health_port_var,
    )

    return InitPlan(
        project_root=project_root,
        project_name=project_name,
        prefix=prefix,
        compose_file=compose_file,
        compose_path=compose_path,
        services=services,
        obs_services=obs_services,
        app_services=app_services,
        ports=ports,
        health_endpoint=health_endpoint,
        health_port_var=health_port_var,
        toml_content=toml_content,
        env_var_candidates=env_var_candidates,
        file_mount_candidates=file_mount_candidates,
    )


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


def detect_env_vars(
    compose_content: str,
    known_vars: set[str],
) -> list[EnvVarCandidate]:
    """Find ${VAR} references in compose text, subtract known vars.

    Returns candidates for [sandbox.secrets] or [sandbox.env].
    Uses raw text regex to catch references in all contexts.
    """
    # Find all ${VAR} and ${VAR:-default} references
    pattern = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-(.*?))?\}")
    all_refs: dict[str, str | None] = {}
    for match in pattern.finditer(compose_content):
        name = match.group(1)
        default = match.group(2)
        if name not in known_vars:
            # Keep first-seen default (don't overwrite with None)
            if name not in all_refs:
                all_refs[name] = default

    if not all_refs:
        return []

    # Determine which services reference each var via YAML parsing
    yml = YAML()
    data = yml.load(compose_content)
    services_map: dict[str, list[str]] = {name: [] for name in all_refs}

    if data and "services" in data:
        for svc_name, svc in data["services"].items():
            env_block = svc.get("environment")
            if not env_block:
                continue
            # environment can be a list or dict
            env_text = ""
            if isinstance(env_block, list):
                env_text = "\n".join(str(e) for e in env_block)
            elif isinstance(env_block, dict):
                env_text = "\n".join(
                    f"{k}={v}" for k, v in env_block.items()
                )
            for var_name in all_refs:
                if f"${{{var_name}}}" in env_text or (
                    f"${{{var_name}:-" in env_text
                ):
                    services_map[var_name].append(svc_name)

    return [
        EnvVarCandidate(
            name=name,
            services=services_map.get(name, []),
            default=default,
        )
        for name, default in sorted(all_refs.items())
    ]


def detect_gitignored_mounts(
    compose_content: str,
    project_root: Path,
) -> list[FileMountCandidate]:
    """Find bind mounts to gitignored files.

    Uses `git check-ignore` for correct gitignore interpretation.
    Skips named volumes (no path separator in host part).
    """
    yml = YAML()
    data = yml.load(compose_content)
    if not data or "services" not in data:
        return []

    # Collect top-level named volumes
    named_volumes = set(data.get("volumes", {}).keys()) if data.get(
        "volumes"
    ) else set()

    candidates: list[FileMountCandidate] = []

    for svc_name, svc in data["services"].items():
        for vol in svc.get("volumes", []):
            vol_str = str(vol)
            parts = vol_str.split(":")
            if len(parts) < 2:
                continue

            host_part = parts[0]
            container_part = parts[1]

            # Skip named volumes
            if host_part in named_volumes:
                continue
            # Bind mounts start with ./ or / or contain /
            if not (
                host_part.startswith("./")
                or host_part.startswith("/")
                or "/" in host_part
                or host_part.startswith(".")
            ):
                continue

            # Normalize: strip leading ./
            rel_path = host_part.removeprefix("./")

            # Check if gitignored
            try:
                result = subprocess.run(
                    ["git", "check-ignore", "-q", rel_path],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=project_root,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

            if result.returncode != 0:
                continue  # Not ignored

            # Check source existence and .example variant
            source_path = project_root / rel_path
            source_exists = source_path.is_file()

            example_path = None
            example_exists = False
            for suffix in [".example", ".sample", ".template"]:
                candidate_example = project_root / f"{rel_path}{suffix}"
                if candidate_example.is_file():
                    example_exists = True
                    example_path = f"{rel_path}{suffix}"
                    break

            candidates.append(
                FileMountCandidate(
                    host_path=rel_path,
                    container_path=container_part,
                    service=svc_name,
                    source_exists=source_exists,
                    example_exists=example_exists,
                    example_path=example_path,
                )
            )

    return candidates


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
    env: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
    files: dict[str, str] | None = None,
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

    if env:
        lines.append("")
        lines.append("[sandbox.env]")
        for key, val in sorted(env.items()):
            lines.append(f'{key} = "{val}"')

    if secrets:
        lines.append("")
        lines.append("[sandbox.secrets]")
        for key, val in sorted(secrets.items()):
            lines.append(f'{key} = "{val}"')

    if files:
        lines.append("")
        lines.append("[sandbox.files]")
        for dest, src in sorted(files.items()):
            lines.append(f'"{dest}" = "{src}"')

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


def _git_toplevel() -> Path | None:
    """Return the git repository toplevel directory, or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _format_dry_run_output(plan: InitPlan) -> str:
    """Format the dry-run output for display."""
    lines = [
        f"Project: {plan.project_name}",
        f"Prefix: {plan.prefix}",
        f"Compose: {plan.compose_file}",
        "",
        "Services detected:",
    ]

    for name, svc in plan.services.items():
        ports_str = ", ".join(str(p["host"]) for p in svc["ports"])
        label = ""
        if name in plan.obs_services:
            label = " (observability — will be commented out)"
        lines.append(f"  {name}: ports [{ports_str}]{label}")

    if not plan.services:
        lines.append("  (none)")

    lines.append("")
    lines.append("Planned infra.toml:")
    for toml_line in plan.toml_content.splitlines():
        lines.append(f"  {toml_line}")

    lines.append("")
    lines.append("Compose changes:")
    for var_name, port in plan.ports.items():
        lines.append(
            f"  - Parameterize port {port}"
            f" → ${{{var_name}:-{port}}}"
        )
    for obs_name in plan.obs_services:
        lines.append(f"  - Comment out service: {obs_name}")
    if plan.obs_services:
        lines.append("  - Remove depends_on references to obs services")
    if plan.ports or plan.obs_services:
        lines.append("  - Add kinfra header comment")
        lines.append(
            f"  - Backup: {plan.compose_file}.bak"
        )

    if plan.env_var_candidates:
        lines.append("")
        lines.append("Environment variables (provisioning):")
        for c in plan.env_var_candidates:
            default_info = f" (default: {c.default})" if c.default else ""
            lines.append(f"  {c.name} \u2192 ${c.name}{default_info}")

    if plan.file_mount_candidates:
        lines.append("")
        lines.append("Config files (provisioning):")
        for fc in plan.file_mount_candidates:
            lines.append(f"  {fc.host_path} \u2190 {fc.host_path}")

    lines.append("")
    lines.append("No files written (dry run).")
    return "\n".join(lines)


def _resolve_provisioning_auto(
    plan: InitPlan,
) -> tuple[dict[str, str], dict[str, str]]:
    """Auto-resolve provisioning candidates.

    Env vars → $VAR_NAME (host environment) as secrets.
    Gitignored mounts → copy from main repo if source exists.

    Returns (secrets, files).
    """
    secrets: dict[str, str] = {}
    files: dict[str, str] = {}

    for ec in plan.env_var_candidates:
        secrets[ec.name] = f"${ec.name}"

    for fc in plan.file_mount_candidates:
        if fc.source_exists:
            files[fc.host_path] = fc.host_path
        elif fc.example_exists and fc.example_path:
            files[fc.host_path] = fc.example_path

    return secrets, files


def _format_check_output(plan: InitPlan) -> str:
    """Format --check output for an already-onboarded project."""
    lines = [f"Project: {plan.project_name} (already onboarded)"]

    has_gaps = False

    if plan.env_var_candidates:
        has_gaps = True
        lines.append("")
        lines.append(
            "\u26a0 Undeclared environment variables in compose:"
        )
        for c in plan.env_var_candidates:
            svc_info = (
                f" ({', '.join(c.services)})"
                if c.services
                else ""
            )
            lines.append(f"  {c.name}{svc_info}")

    if plan.file_mount_candidates:
        has_gaps = True
        lines.append("")
        lines.append(
            "\u26a0 Gitignored volume mounts without [sandbox.files]:"
        )
        for fc in plan.file_mount_candidates:
            lines.append(
                f"  {fc.host_path} \u2192 {fc.service} "
                f"(./{fc.host_path}:{fc.container_path})"
            )

    if has_gaps:
        lines.append("")
        lines.append("Suggested additions to .devops-ai/infra.toml:")
        if plan.env_var_candidates:
            lines.append("")
            lines.append("  [sandbox.secrets]")
            for ec in plan.env_var_candidates:
                lines.append(
                    f'  {ec.name} = "${ec.name}"'
                    f"   # or op://vault/item/field"
                )
        if plan.file_mount_candidates:
            lines.append("")
            lines.append("  [sandbox.files]")
            for fc in plan.file_mount_candidates:
                source = fc.host_path
                if not fc.source_exists and fc.example_path:
                    source = fc.example_path
                lines.append(f'  "{fc.host_path}" = "{source}"')
    else:
        lines.append("")
        lines.append("All good \u2014 no gaps detected.")

    return "\n".join(lines)


def init_command(
    project_root: Path | None = None,
    dry_run: bool = False,
    auto: bool = False,
    health_endpoint: str | None = None,
    check: bool = False,
) -> int:
    """Run the init flow. Returns exit code.

    With no flags: interactive mode (prompts for all values).
    With --auto: accept all detected defaults, no prompts.
    With --dry-run: preview changes without writing files.
    With --health-endpoint: override the default health endpoint.
    With --check: report provisioning gaps on already-onboarded project.
    """
    if project_root is None:
        project_root = (
            find_project_root() or _git_toplevel() or Path.cwd()
        )

    # Check for existing config
    exists, existing_name = check_existing_config(project_root)

    # --check mode: report gaps and exit
    if check:
        plan = detect_project(project_root)
        typer.echo(_format_check_output(plan))
        return 0

    if exists:
        if auto:
            typer.echo(
                f"Updating existing config for '{existing_name}'."
            )
        else:
            typer.echo(
                f"Found existing config for '{existing_name}'."
            )
            if not typer.confirm(
                "Update existing config?", default=False
            ):
                typer.echo("Aborted.")
                return 0

    # Check Docker
    if not check_docker_running():
        typer.echo(
            "Warning: Docker not running. "
            "Init can proceed, but sandbox features need Docker."
        )

    # Run detection pipeline
    plan = detect_project(project_root)

    # Apply --health-endpoint override
    if health_endpoint is not None:
        plan.health_endpoint = health_endpoint

    # Auto-resolve provisioning candidates
    auto_secrets, auto_files = _resolve_provisioning_auto(plan)

    # Regenerate toml with provisioning sections
    plan.toml_content = generate_infra_toml(
        project_name=plan.project_name,
        prefix=plan.prefix,
        compose_file=plan.compose_file,
        ports=plan.ports,
        health_endpoint=plan.health_endpoint,
        health_port_var=plan.health_port_var,
        secrets=auto_secrets or None,
        files=auto_files or None,
    )

    if auto:
        # Use detected defaults directly — no prompts
        if dry_run:
            typer.echo(_format_dry_run_output(plan))
            return 0

        # Write config and rewrite compose
        config_dir = project_root / ".devops-ai"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "infra.toml").write_text(plan.toml_content)
        typer.echo("\nConfig written to .devops-ai/infra.toml")

        if plan.compose_path.exists() and (
            plan.ports or plan.obs_services
        ):
            rewrite_compose(
                plan.compose_path, plan.ports, plan.obs_services
            )
            typer.echo(
                f"Compose file updated: {plan.compose_file}"
            )
        return 0

    # Interactive mode — prompt for overrides
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

    # Display detected services
    if plan.services:
        typer.echo(f"\nDetected {len(plan.services)} services:")
        for name, svc in plan.services.items():
            ports_str = ", ".join(
                str(p["host"]) for p in svc["ports"]
            )
            label = (
                " (observability)"
                if name in plan.obs_services
                else ""
            )
            typer.echo(f"  {name}: ports [{ports_str}]{label}")

    if plan.obs_services:
        typer.echo(
            f"\nObservability services ({', '.join(plan.obs_services)}) "
            "will be provided by kinfra's shared stack."
        )

    project_name = typer.prompt(
        "Project name", default=plan.project_name
    )
    prefix = typer.prompt("Worktree prefix", default=project_name)

    prompted_health: str | None = typer.prompt(
        "Health check endpoint (empty to skip)",
        default=health_endpoint or "/api/v1/health",
    )
    if not prompted_health:
        prompted_health = None

    # Rebuild port map and toml with possibly-overridden values
    compose_path = project_root / compose_file
    services: dict[str, dict[str, Any]] = {}
    if compose_path.exists():
        services = detect_services_from_compose(
            compose_path.read_text()
        )
    obs_services = identify_observability_services(services)
    app_services = {
        k: v for k, v in services.items() if k not in obs_services
    }

    ports: dict[str, int] = {}
    health_port_var: str | None = None
    for svc_name, svc in app_services.items():
        for port_info in svc["ports"]:
            var_name = (
                f"{prefix.upper().replace('-', '_')}"
                f"_{svc_name.upper().replace('-', '_')}_PORT"
            )
            ports[var_name] = port_info["host"]
            if health_port_var is None and prompted_health:
                health_port_var = var_name

    toml_content = generate_infra_toml(
        project_name=project_name,
        prefix=prefix,
        compose_file=compose_file,
        ports=ports,
        health_endpoint=prompted_health,
        health_port_var=health_port_var,
    )

    if dry_run:
        # Build a plan with user-overridden values for display
        overridden_plan = InitPlan(
            project_root=project_root,
            project_name=project_name,
            prefix=prefix,
            compose_file=compose_file,
            compose_path=compose_path,
            services=services,
            obs_services=obs_services,
            app_services=app_services,
            ports=ports,
            health_endpoint=prompted_health,
            health_port_var=health_port_var,
            toml_content=toml_content,
        )
        typer.echo(_format_dry_run_output(overridden_plan))
        return 0

    config_dir = project_root / ".devops-ai"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "infra.toml").write_text(toml_content)

    typer.echo("\nConfig written to .devops-ai/infra.toml")

    # Rewrite compose file with parameterized ports and commented obs services
    if compose_path.exists() and (ports or obs_services):
        rewrite_compose(compose_path, ports, obs_services)
        typer.echo(f"Compose file updated: {compose_file}")

    return 0
