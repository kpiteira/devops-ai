"""Tests for slot registry — persistence, allocation, claim/release, stale cleanup."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from devops_ai.config import InfraConfig, ServicePort
from devops_ai.registry import (
    Registry,
    SlotInfo,
    allocate_slot,
    claim_slot,
    clean_stale_entries,
    get_slot_for_worktree,
    load_registry,
    release_slot,
    save_registry,
)


def _config_with_ports(*ports: tuple[str, int]) -> InfraConfig:
    """Helper: create InfraConfig with given (env_var, base_port) pairs."""
    return InfraConfig(
        project_name="test-project",
        prefix="test",
        has_sandbox=True,
        ports=[ServicePort(env_var=e, base_port=p) for e, p in ports],
    )


class TestLoadRegistry:
    def test_load_empty_no_file(self, tmp_path: Path) -> None:
        """No file → empty registry."""
        reg = load_registry(tmp_path / "registry.json")
        assert reg.version == 1
        assert reg.slots == {}

    def test_load_existing(self, tmp_path: Path) -> None:
        """Valid JSON → correct Registry."""
        path = tmp_path / "registry.json"
        data = {
            "version": 1,
            "slots": {
                "1": {
                    "slot_id": 1,
                    "project": "myproj",
                    "worktree_path": "/tmp/wt",
                    "slot_dir": "/tmp/slot",
                    "compose_file_copy": "/tmp/slot/docker-compose.yml",
                    "ports": {"API_PORT": 8081},
                    "claimed_at": "2025-01-01T00:00:00",
                    "status": "running",
                },
            },
        }
        path.write_text(json.dumps(data))
        reg = load_registry(path)
        assert 1 in reg.slots
        assert reg.slots[1].project == "myproj"
        assert reg.slots[1].ports == {"API_PORT": 8081}


class TestSaveAndReload:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "registry.json"
        reg = Registry(version=1, slots={})
        slot = SlotInfo(
            slot_id=3,
            project="proj",
            worktree_path="/wt",
            slot_dir="/slot",
            compose_file_copy="/slot/compose.yml",
            ports={"P": 8083},
            claimed_at="2025-06-01T12:00:00",
            status="running",
        )
        reg.slots[3] = slot
        save_registry(reg, path)
        loaded = load_registry(path)
        assert 3 in loaded.slots
        assert loaded.slots[3].project == "proj"
        assert loaded.slots[3].ports == {"P": 8083}


class TestClaimAndRelease:
    def test_claim_adds_release_removes(self, tmp_path: Path) -> None:
        path = tmp_path / "registry.json"
        reg = Registry(version=1, slots={})
        slot_info = SlotInfo(
            slot_id=5,
            project="proj",
            worktree_path="/wt",
            slot_dir="/slot",
            compose_file_copy="/slot/compose.yml",
            ports={"P": 8085},
            claimed_at="2025-01-01T00:00:00",
            status="running",
        )
        claim_slot(reg, slot_info, path)
        assert 5 in reg.slots

        release_slot(reg, 5, path)
        assert 5 not in reg.slots


class TestAllocateSlot:
    def test_skips_claimed(self) -> None:
        """Slot 1 claimed → allocates slot 2."""
        config = _config_with_ports(("API_PORT", 8080))
        reg = Registry(version=1, slots={})
        reg.slots[1] = SlotInfo(
            slot_id=1,
            project="other",
            worktree_path="/wt",
            slot_dir="/slot",
            compose_file_copy="/slot/compose.yml",
            ports={"API_PORT": 8081},
            claimed_at="2025-01-01T00:00:00",
            status="running",
        )
        with patch(
            "devops_ai.registry.check_ports_available", return_value=[]
        ):
            slot_id, ports = allocate_slot(reg, config)
        assert slot_id == 2
        assert ports == {"API_PORT": 8082}

    def test_skips_port_conflict(self) -> None:
        """Mock port in use → skips slot."""
        from devops_ai.ports import PortConflict

        config = _config_with_ports(("API_PORT", 8080))
        reg = Registry(version=1, slots={})

        # Slot 1 has port conflict, slot 2 is free
        def mock_check(ports: dict[str, int]) -> list[PortConflict]:
            if ports.get("API_PORT") == 8081:
                return [PortConflict("API_PORT", 8081, "in use")]
            return []

        with patch(
            "devops_ai.registry.check_ports_available", side_effect=mock_check
        ):
            slot_id, ports = allocate_slot(reg, config)
        assert slot_id == 2

    def test_exhausted(self) -> None:
        """All 100 claimed → error."""
        config = _config_with_ports(("API_PORT", 8080))
        reg = Registry(version=1, slots={})
        for i in range(1, 101):
            reg.slots[i] = SlotInfo(
                slot_id=i,
                project="proj",
                worktree_path=f"/wt{i}",
                slot_dir=f"/slot{i}",
                compose_file_copy=f"/slot{i}/compose.yml",
                ports={"API_PORT": 8080 + i},
                claimed_at="2025-01-01T00:00:00",
                status="running",
            )
        with patch(
            "devops_ai.registry.check_ports_available", return_value=[]
        ):
            try:
                allocate_slot(reg, config)
                raise AssertionError("Should have raised")
            except RuntimeError as e:
                assert "No slots available" in str(e)


class TestGetSlotForWorktree:
    def test_found(self) -> None:
        reg = Registry(version=1, slots={})
        reg.slots[2] = SlotInfo(
            slot_id=2,
            project="proj",
            worktree_path="/my/worktree",
            slot_dir="/slot",
            compose_file_copy="/slot/compose.yml",
            ports={},
            claimed_at="2025-01-01T00:00:00",
            status="running",
        )
        result = get_slot_for_worktree(reg, Path("/my/worktree"))
        assert result is not None
        assert result.slot_id == 2

    def test_not_found(self) -> None:
        reg = Registry(version=1, slots={})
        result = get_slot_for_worktree(reg, Path("/nonexistent"))
        assert result is None


class TestCleanStale:
    def test_missing_worktree_cleaned(self, tmp_path: Path) -> None:
        """Worktree path doesn't exist → cleaned."""
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        reg = Registry(version=1, slots={})
        reg.slots[1] = SlotInfo(
            slot_id=1,
            project="proj",
            worktree_path="/nonexistent/worktree",
            slot_dir=str(slot_dir),
            compose_file_copy=str(slot_dir / "compose.yml"),
            ports={},
            claimed_at="2025-01-01T00:00:00",
            status="running",
        )
        removed = clean_stale_entries(reg)
        assert 1 not in reg.slots
        assert len(removed) == 1

    def test_missing_slot_dir_cleaned(self, tmp_path: Path) -> None:
        """Slot dir doesn't exist → cleaned."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        reg = Registry(version=1, slots={})
        reg.slots[1] = SlotInfo(
            slot_id=1,
            project="proj",
            worktree_path=str(wt),
            slot_dir="/nonexistent/slot",
            compose_file_copy="/nonexistent/slot/compose.yml",
            ports={},
            claimed_at="2025-01-01T00:00:00",
            status="running",
        )
        removed = clean_stale_entries(reg)
        assert 1 not in reg.slots
        assert len(removed) == 1

    def test_both_exist_preserved(self, tmp_path: Path) -> None:
        """Both paths exist → entry preserved."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        reg = Registry(version=1, slots={})
        reg.slots[1] = SlotInfo(
            slot_id=1,
            project="proj",
            worktree_path=str(wt),
            slot_dir=str(slot_dir),
            compose_file_copy=str(slot_dir / "compose.yml"),
            ports={},
            claimed_at="2025-01-01T00:00:00",
            status="running",
        )
        removed = clean_stale_entries(reg)
        assert 1 in reg.slots
        assert len(removed) == 0
