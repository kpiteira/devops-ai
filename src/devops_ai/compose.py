"""Compose file parameterization — port vars, observability commenting, headers."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ruamel.yaml import YAML

HEADER_COMMENT = """\
# =============================================================================
# kinfra-managed Docker Compose file
# =============================================================================
# Host ports use environment variables for sandbox isolation. Each sandbox slot
# offsets ports by its slot number. Default values (after :-) are the base ports
# for running without kinfra. See .devops-ai/infra.toml for configuration.
#
# To run without kinfra: docker compose up -d (defaults apply)
# To run in sandbox:     kinfra impl <feature/milestone>
# =============================================================================

"""

OBS_COMMENT = """\
  # -------------------------------------------------------------------------
  # Observability services below are commented out because kinfra provides
  # a shared observability stack. To use standalone (without kinfra), uncomment.
  # -------------------------------------------------------------------------
"""


def parameterize_ports(
    yaml_content: str, port_map: dict[str, int]
) -> str:
    """Replace hardcoded host ports with ${VAR:-default} syntax.

    port_map maps env var names to base port numbers.
    Only replaces ports that match values in port_map.
    Skips ports that already contain ${.
    """
    result = yaml_content
    for var_name, port in port_map.items():
        # Match "PORT:PORT" patterns (quoted or unquoted)
        # but skip already-parameterized ones
        pattern = re.compile(
            rf'(?<!\${{)"?{port}:{port}"?'
        )
        replacement = f'"${{{var_name}:-{port}}}:{port}"'
        result = pattern.sub(replacement, result)
    return result


def comment_out_services(
    yaml_content: str, service_names: list[str]
) -> str:
    """Comment out entire service blocks for the given service names."""
    if not service_names:
        return yaml_content

    # Parse to find service boundaries
    yml = YAML()
    data = yml.load(yaml_content)
    if not data or "services" not in data:
        return yaml_content

    lines = yaml_content.splitlines(keepends=True)
    result_lines: list[str] = []
    in_obs_service = False
    obs_indent = 0
    added_obs_header = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        # Detect start of a service block (2 spaces + name + colon)
        svc_match = re.match(r"^  (\S+):", stripped)
        if svc_match:
            svc_name = svc_match.group(1)
            if svc_name in service_names:
                if not added_obs_header:
                    result_lines.append("\n")
                    result_lines.append(OBS_COMMENT)
                    added_obs_header = True
                in_obs_service = True
                obs_indent = 2
                # Comment this line
                result_lines.append(f"  # {stripped.lstrip()}\n")
                i += 1
                continue
            else:
                in_obs_service = False

        if in_obs_service:
            # Check if this line is still inside the service block
            if stripped == "":
                # Blank line — could end the block
                in_obs_service = False
                result_lines.append(line)
            elif line[0] == " " and len(line) - len(
                line.lstrip()
            ) > obs_indent:
                # Indented deeper — still in service
                result_lines.append(
                    f"  # {stripped.lstrip()}\n"
                )
            elif (
                line[0] == " "
                and len(line) - len(line.lstrip()) == obs_indent
                and not re.match(r"^  \S+:", stripped)
            ):
                # Same indent, continuation
                result_lines.append(
                    f"  # {stripped.lstrip()}\n"
                )
            else:
                in_obs_service = False
                result_lines.append(line)
        else:
            result_lines.append(line)
        i += 1

    return "".join(result_lines)


def remove_depends_on(
    yaml_content: str, service_names: list[str]
) -> str:
    """Remove depends_on list entries referencing obs service names.

    Uses line-based approach to preserve original formatting.
    Removes the entire depends_on block if all entries are removed.
    """
    if not service_names:
        return yaml_content

    lines = yaml_content.splitlines(keepends=True)
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        # Detect "depends_on:" line
        if re.match(r"^\s+depends_on:\s*$", stripped):
            depends_indent = len(line) - len(line.lstrip())
            dep_lines: list[str] = []
            j = i + 1
            # Collect all list items under depends_on
            while j < len(lines):
                dep_line = lines[j]
                dep_stripped = dep_line.rstrip()
                if dep_stripped == "":
                    break
                dep_line_indent = len(dep_line) - len(
                    dep_line.lstrip()
                )
                if dep_line_indent <= depends_indent:
                    break
                dep_lines.append(dep_line)
                j += 1

            # Filter out obs service references
            kept = []
            for dl in dep_lines:
                ds = dl.strip().lstrip("- ").strip()
                if ds not in service_names:
                    kept.append(dl)

            if kept:
                result.append(line)
                result.extend(kept)
            # else: drop entire depends_on block
            i = j
            continue

        result.append(line)
        i += 1

    return "".join(result)


def add_header_comment(yaml_content: str) -> str:
    """Add the kinfra header comment block to the top of the file."""
    # Don't add if already present
    if "kinfra-managed" in yaml_content:
        return yaml_content
    return HEADER_COMMENT + yaml_content


def rewrite_compose(
    compose_path: Path,
    port_map: dict[str, int],
    obs_services: list[str],
) -> None:
    """Rewrite a compose file with parameterized ports and commented obs services.

    Creates a .bak backup before modifying.
    """
    original = compose_path.read_text()

    # Backup
    backup_path = compose_path.with_suffix(".yml.bak")
    if not backup_path.exists():
        shutil.copy2(compose_path, backup_path)

    # Apply transformations in order
    result = original
    result = remove_depends_on(result, obs_services)
    result = parameterize_ports(result, port_map)
    result = comment_out_services(result, obs_services)
    result = add_header_comment(result)

    compose_path.write_text(result)
