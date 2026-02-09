"""Tests for sandbox manager — slot dir, env file, override, compose copy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from devops_ai.config import InfraConfig, MountEntry, ServicePort
from devops_ai.registry import SlotInfo
from devops_ai.sandbox import (
    copy_compose_to_slot,
    create_slot_dir,
    generate_env_file,
    generate_override,
    remove_slot_dir,
)


def _slot(
    slot_id: int = 1,
    project: str = "myproj",
    ports: dict[str, int] | None = None,
) -> SlotInfo:
    return SlotInfo(
        slot_id=slot_id,
        project=project,
        worktree_path="/tmp/wt",
        slot_dir="/tmp/slot",
        compose_file_copy="/tmp/slot/docker-compose.yml",
        ports=ports or {"API_PORT": 8081},
        claimed_at="2025-01-01T00:00:00",
        status="running",
    )


def _config(
    ports: list[tuple[str, int]] | None = None,
    code_mounts: list[MountEntry] | None = None,
    code_mount_targets: list[str] | None = None,
    shared_mounts: list[MountEntry] | None = None,
    shared_mount_targets: list[str] | None = None,
) -> InfraConfig:
    return InfraConfig(
        project_name="myproj",
        prefix="myproj",
        has_sandbox=True,
        ports=[
            ServicePort(e, p) for e, p in (ports or [("API_PORT", 8080)])
        ],
        code_mounts=code_mounts or [],
        code_mount_targets=code_mount_targets or [],
        shared_mounts=shared_mounts or [],
        shared_mount_targets=shared_mount_targets or [],
    )


class TestCreateSlotDir:
    def test_creates_at_expected_path(self, tmp_path: Path) -> None:
        result = create_slot_dir("myproj", 3, base=tmp_path)
        assert result == tmp_path / "myproj-3"
        assert result.is_dir()


class TestRemoveSlotDir:
    def test_removes_dir(self, tmp_path: Path) -> None:
        slot_dir = tmp_path / "myproj-1"
        slot_dir.mkdir()
        (slot_dir / "somefile").write_text("data")
        remove_slot_dir(slot_dir)
        assert not slot_dir.exists()


class TestCopyCompose:
    def test_copies_to_slot_dir(self, tmp_path: Path) -> None:
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("services:\n  app:\n    image: python\n")
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        result = copy_compose_to_slot(compose, slot_dir)
        assert result.exists()
        assert result.read_text() == compose.read_text()


class TestGenerateEnvFile:
    def test_content(self, tmp_path: Path) -> None:
        slot = _slot(slot_id=2, ports={"API_PORT": 8082, "DB_PORT": 5434})
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        result = generate_env_file(_config(), slot, slot_dir)
        content = result.read_text()
        assert "COMPOSE_PROJECT_NAME=myproj-slot-2" in content
        assert "API_PORT=8082" in content
        assert "DB_PORT=5434" in content

    def test_port_offset(self, tmp_path: Path) -> None:
        slot = _slot(slot_id=5, ports={"API_PORT": 8085})
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        result = generate_env_file(_config(), slot, slot_dir)
        content = result.read_text()
        assert "API_PORT=8085" in content


class TestGenerateOverride:
    def test_code_mounts(self, tmp_path: Path) -> None:
        """Volumes section has absolute worktree paths."""
        config = _config(
            code_mounts=[MountEntry("src/", "/app/src")],
            code_mount_targets=["app"],
        )
        slot = _slot()
        wt = tmp_path / "worktree"
        wt.mkdir()
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()

        with patch(
            "devops_ai.sandbox._observability_network_exists",
            return_value=False,
        ):
            result = generate_override(
                config, slot, wt, main_repo, slot_dir
            )
        content = result.read_text()
        assert f"{wt}/src/:/app/src" in content

    def test_shared_mounts(self, tmp_path: Path) -> None:
        """Volumes section has absolute main_repo paths."""
        config = _config(
            shared_mounts=[MountEntry("data/", "/app/data")],
            shared_mount_targets=["app"],
        )
        slot = _slot()
        wt = tmp_path / "worktree"
        wt.mkdir()
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()

        with patch(
            "devops_ai.sandbox._observability_network_exists",
            return_value=False,
        ):
            result = generate_override(
                config, slot, wt, main_repo, slot_dir
            )
        content = result.read_text()
        assert f"{main_repo}/data/:/app/data" in content

    def test_readonly_mount(self, tmp_path: Path) -> None:
        """:ro preserved in override."""
        config = _config(
            code_mounts=[MountEntry("config/", "/app/config", readonly=True)],
            code_mount_targets=["app"],
        )
        slot = _slot()
        wt = tmp_path / "worktree"
        wt.mkdir()
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()

        with patch(
            "devops_ai.sandbox._observability_network_exists",
            return_value=False,
        ):
            result = generate_override(
                config, slot, wt, main_repo, slot_dir
            )
        content = result.read_text()
        assert f"{wt}/config/:/app/config:ro" in content

    def test_header_comment(self, tmp_path: Path) -> None:
        config = _config()
        slot = _slot()
        wt = tmp_path / "worktree"
        wt.mkdir()
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()

        with patch(
            "devops_ai.sandbox._observability_network_exists",
            return_value=False,
        ):
            result = generate_override(
                config, slot, wt, main_repo, slot_dir
            )
        content = result.read_text()
        assert "Generated by kinfra" in content
        assert str(wt) in content

    def test_multiple_targets(self, tmp_path: Path) -> None:
        """Multiple services each get their mounts."""
        config = _config(
            code_mounts=[MountEntry("src/", "/app/src")],
            code_mount_targets=["app", "worker"],
        )
        slot = _slot()
        wt = tmp_path / "worktree"
        wt.mkdir()
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()

        with patch(
            "devops_ai.sandbox._observability_network_exists",
            return_value=False,
        ):
            result = generate_override(
                config, slot, wt, main_repo, slot_dir
            )
        content = result.read_text()
        # Both services should appear
        assert "  app:" in content
        assert "  worker:" in content

    def test_no_observability_network(self, tmp_path: Path) -> None:
        """Missing observability network → no network section."""
        config = _config(
            code_mounts=[MountEntry("src/", "/app/src")],
            code_mount_targets=["app"],
        )
        slot = _slot()
        wt = tmp_path / "worktree"
        wt.mkdir()
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()

        with patch(
            "devops_ai.sandbox._observability_network_exists",
            return_value=False,
        ):
            result = generate_override(
                config, slot, wt, main_repo, slot_dir
            )
        content = result.read_text()
        assert "devops-ai-observability" not in content
        assert "OTEL_EXPORTER" not in content
