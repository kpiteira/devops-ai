"""E2E test fixtures — real git repos, real Docker containers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def pull_test_image() -> None:
    """Pre-pull python:3.12-slim so health gate doesn't time out."""
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("Docker is not running")

    subprocess.run(
        ["docker", "pull", "python:3.12-slim"],
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.fixture()
def e2e_project(tmp_path_factory: pytest.TempPathFactory):  # noqa: ANN201
    """Create a fully-configured test project with git repo, compose, and config.

    Yields dict with repo_root, worktree_path, project_name, expected_port, etc.
    Teardown stops containers, cleans registry/slots, removes worktree.
    """
    base_dir = tmp_path_factory.mktemp("kinfra-e2e")
    repo_root = base_dir / "repo"
    repo_root.mkdir()

    project_name = "e2e-test"
    prefix = "e2e-test"
    feature = "e2e-feat"
    milestone = "M1"
    base_port = 18080

    # --- Setup: git repo ---
    subprocess.run(
        ["git", "init"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )

    # --- Setup: parameterized compose file ---
    compose = (
        "services:\n"
        "  web:\n"
        "    image: python:3.12-slim\n"
        f"    command: python -m http.server {base_port}\n"
        "    ports:\n"
        f'      - "${{APP_PORT:-{base_port}}}:{base_port}"\n'
    )
    (repo_root / "docker-compose.yml").write_text(compose)

    # --- Setup: .devops-ai/infra.toml ---
    devops_dir = repo_root / ".devops-ai"
    devops_dir.mkdir()
    infra_toml = (
        "[project]\n"
        f'name = "{project_name}"\n'
        f'prefix = "{prefix}"\n'
        "\n"
        "[sandbox]\n"
        'compose_file = "docker-compose.yml"\n'
        "\n"
        "[sandbox.health]\n"
        'endpoint = "/"\n'
        'port_var = "APP_PORT"\n'
        "timeout = 60\n"
        "\n"
        "[sandbox.ports]\n"
        f"APP_PORT = {base_port}\n"
    )
    (devops_dir / "infra.toml").write_text(infra_toml)

    # --- Setup: milestone file ---
    impl_dir = repo_root / "docs" / "designs" / feature / "implementation"
    impl_dir.mkdir(parents=True)
    (impl_dir / f"{milestone}_foundation.md").write_text(
        f"# {milestone} Foundation\n"
    )

    # --- Setup: commit everything ---
    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "e2e setup"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )

    worktree_path = (
        repo_root.parent / f"{prefix}-impl-{feature}-{milestone}"
    )

    info = {
        "repo_root": repo_root,
        "worktree_path": worktree_path,
        "project_name": project_name,
        "prefix": prefix,
        "feature": feature,
        "milestone": milestone,
        "base_port": base_port,
        "expected_port": base_port + 1,
    }

    yield info

    # --- Teardown (always runs) ---
    _cleanup_e2e(info)


def _cleanup_e2e(info: dict[str, object]) -> None:
    """Best-effort cleanup of all E2E artifacts."""
    project_name = str(info["project_name"])
    repo_root = info["repo_root"]
    worktree_path = info["worktree_path"]

    assert isinstance(repo_root, Path)
    assert isinstance(worktree_path, Path)

    # 1. Stop Docker containers via slot dir compose files
    slots_base = Path.home() / ".devops-ai" / "slots"
    if slots_base.exists():
        for slot_dir in slots_base.glob(f"{project_name}-*"):
            compose_copy = slot_dir / "docker-compose.yml"
            override = slot_dir / "docker-compose.override.yml"
            env_file = slot_dir / ".env.sandbox"
            if all(f.exists() for f in (compose_copy, override, env_file)):
                subprocess.run(
                    [
                        "docker", "compose",
                        "-f", str(compose_copy),
                        "-f", str(override),
                        "--env-file", str(env_file),
                        "down", "--remove-orphans",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            shutil.rmtree(slot_dir, ignore_errors=True)

    # 2. Clean registry entries for this project
    registry_path = Path.home() / ".devops-ai" / "registry.json"
    if registry_path.exists():
        try:
            data = json.loads(registry_path.read_text())
            slots = data.get("slots", {})
            cleaned = {
                k: v
                for k, v in slots.items()
                if v.get("project") != project_name
            }
            if len(cleaned) != len(slots):
                data["slots"] = cleaned
                registry_path.write_text(
                    json.dumps(data, indent=2) + "\n"
                )
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Remove worktree
    if worktree_path.exists():
        subprocess.run(
            [
                "git", "worktree", "remove", "--force",
                str(worktree_path),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

    # 4. Prune stale worktree refs
    if repo_root.exists():
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
