"""`kinfra sandbox start` resolves secrets against the main checkout (A5).

A worktree never carries the project's gitignored `.env` — it lives in the main
repository. This needs a real git worktree to be worth anything, so it is an
integration test; only the Docker call is faked.
"""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

from devops_ai.cli.sandbox_cmd import sandbox_start_command

SECRET = "from-the-main-checkout"


def test_dotenv_reference_reads_the_main_repo_not_the_worktree(
    tmp_path: Path,
) -> None:
    main_repo, worktree = _main_repo_with_worktree(tmp_path)
    # The newcomer's setup: gitignored .env, a reference to it in infra.toml.
    (main_repo / ".env").write_text(f"DB_PASSWORD={SECRET}\n")
    assert not (worktree / ".env").exists(), "the worktree must not carry it"

    registry_path, slot_dir = _registry_with_slot(tmp_path, worktree)

    with (
        patch("devops_ai.cli.sandbox_cmd.REGISTRY_PATH", registry_path),
        patch("devops_ai.cli.sandbox_cmd.start_sandbox"),
        patch("devops_ai.cli.sandbox_cmd.run_health_gate", return_value=True),
    ):
        code, msg = sandbox_start_command(worktree_path=worktree)

    assert code == 0, msg
    assert SECRET not in msg, "a resolved value must not be echoed"
    assert (slot_dir / ".env.secrets").read_text() == f"DB_PASSWORD={SECRET}\n"


def test_a_reference_with_nowhere_to_resolve_fails_before_docker(
    tmp_path: Path,
) -> None:
    _, worktree = _main_repo_with_worktree(tmp_path)
    registry_path, slot_dir = _registry_with_slot(tmp_path, worktree)

    with (
        patch("devops_ai.cli.sandbox_cmd.REGISTRY_PATH", registry_path),
        patch("devops_ai.cli.sandbox_cmd.start_sandbox") as docker,
        patch("devops_ai.cli.sandbox_cmd.run_health_gate", return_value=True),
    ):
        code, msg = sandbox_start_command(worktree_path=worktree)

    assert code == 1
    assert "DB_PASSWORD" in msg
    docker.assert_not_called()
    assert not (slot_dir / ".env.secrets").exists()


def test_a_reused_secrets_file_is_tightened_before_the_sandbox_starts(
    tmp_path: Path,
) -> None:
    """Mode at the moment compose reads it is what matters, not mode afterwards."""
    main_repo, worktree = _main_repo_with_worktree(tmp_path)
    registry_path, slot_dir = _registry_with_slot(tmp_path, worktree)

    # A slot materialised before the mode was enforced: same names, mode 644.
    legacy = slot_dir / ".env.secrets"
    legacy.write_text(f"DB_PASSWORD={SECRET}\n")
    legacy.chmod(0o644)

    seen: dict[str, int] = {}

    def record_mode(*_args: object, **_kwargs: object) -> None:
        seen["mode"] = stat.S_IMODE(legacy.stat().st_mode)

    with (
        patch("devops_ai.cli.sandbox_cmd.REGISTRY_PATH", registry_path),
        patch("devops_ai.cli.sandbox_cmd.start_sandbox", side_effect=record_mode),
        patch("devops_ai.cli.sandbox_cmd.run_health_gate", return_value=True),
    ):
        code, msg = sandbox_start_command(worktree_path=worktree)

    assert code == 0, msg
    assert seen["mode"] == 0o600, "compose read the file while it was still 0644"
    assert legacy.read_text() == f"DB_PASSWORD={SECRET}\n", "reuse, not re-resolve"


def test_a_legacy_file_is_tightened_even_when_resolution_fails(
    tmp_path: Path,
) -> None:
    """The RESOLVE path returns before rewriting the file — it must still be 0600."""
    main_repo, worktree = _main_repo_with_worktree(tmp_path)
    registry_path, slot_dir = _registry_with_slot(tmp_path, worktree)
    # No .env in the main repo, so the configured reference cannot resolve.
    legacy = slot_dir / ".env.secrets"
    legacy.write_text("DB_PASSWORD=from-an-older-slot\n")
    legacy.chmod(0o644)
    # A name the config does not declare forces RESOLVE rather than REUSE.
    legacy.write_text("STALE_NAME=old\n")
    legacy.chmod(0o644)

    with (
        patch("devops_ai.cli.sandbox_cmd.REGISTRY_PATH", registry_path),
        patch("devops_ai.cli.sandbox_cmd.start_sandbox") as docker,
        patch("devops_ai.cli.sandbox_cmd.run_health_gate", return_value=True),
    ):
        code, msg = sandbox_start_command(worktree_path=worktree)

    assert code == 1, msg
    docker.assert_not_called()
    assert stat.S_IMODE(legacy.stat().st_mode) == 0o600, (
        "a failed resolution left the old secrets file world-readable"
    )


def _main_repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main_repo = tmp_path / "main"
    main_repo.mkdir()
    for args in (
        ["git", "init"],
        ["git", "config", "user.email", "test@test.com"],
        ["git", "config", "user.name", "Test"],
    ):
        subprocess.run(args, cwd=main_repo, check=True, capture_output=True)

    (main_repo / ".gitignore").write_text(".env\n")
    (main_repo / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: python:3.12-slim\n"
    )
    config_dir = main_repo / ".devops-ai"
    config_dir.mkdir()
    (config_dir / "infra.toml").write_text(
        "[project]\n"
        'name = "myproj"\n'
        'prefix = "myproj"\n'
        "\n"
        "[sandbox]\n"
        'compose_file = "docker-compose.yml"\n'
        "\n"
        "[sandbox.secrets]\n"
        'DB_PASSWORD = "dotenv://.env#DB_PASSWORD"\n'
    )
    subprocess.run(["git", "add", "-A"], cwd=main_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=main_repo, check=True, capture_output=True
    )

    worktree = tmp_path / "myproj-impl-feat-M1"
    subprocess.run(
        ["git", "worktree", "add", "-b", "impl/feat-M1", str(worktree)],
        cwd=main_repo,
        check=True,
        capture_output=True,
    )
    return main_repo, worktree


def _registry_with_slot(tmp_path: Path, worktree: Path) -> tuple[Path, Path]:
    registry_path = tmp_path / "registry.json"
    slot_dir = tmp_path / "slots" / "myproj-1"
    slot_dir.mkdir(parents=True)
    (slot_dir / ".env.sandbox").write_text("COMPOSE_PROJECT_NAME=myproj-slot-1\n")
    registry_path.write_text(
        json.dumps(
            {
                "slots": {
                    "1": {
                        "slot_id": 1,
                        "project": "myproj",
                        "worktree_path": str(worktree),
                        "slot_dir": str(slot_dir),
                        "compose_file_copy": str(slot_dir / "docker-compose.yml"),
                        "ports": {"API_PORT": 8081},
                        "claimed_at": "2025-01-01T00:00:00",
                        "status": "stopped",
                    }
                }
            }
        )
    )
    return registry_path, slot_dir
