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


class TestAtomicWrite:
    def test_save_uses_atomic_rename(self, tmp_path: Path) -> None:
        """save_registry writes to temp file then renames."""
        path = tmp_path / "registry.json"
        reg = Registry(version=1, slots={})
        save_registry(reg, path)
        # File should exist and be valid JSON
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["version"] == 1

    def test_save_no_partial_file_on_disk(self, tmp_path: Path) -> None:
        """After save, no .tmp file should remain."""
        path = tmp_path / "registry.json"
        reg = Registry(version=1, slots={})
        save_registry(reg, path)
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_corrupt_file_recovers(self, tmp_path: Path) -> None:
        """Partial JSON file → load returns empty registry."""
        path = tmp_path / "registry.json"
        path.write_text('{"version": 1, "slots": {')  # truncated
        reg = load_registry(path)
        assert reg.slots == {}


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


class TestClaimIsAtomic:
    def _info(self, slot_id: int, wt: str) -> SlotInfo:
        return SlotInfo(
            slot_id=slot_id, project="p", worktree_path=wt, slot_dir="/s",
            compose_file_copy="", ports={}, claimed_at="", status="provisioning",
        )

    def test_second_claimant_is_refused(self, tmp_path) -> None:
        """Two processes allocate the same free id; only the first claims it."""
        from devops_ai.registry import SlotClaimedError

        path = tmp_path / "registry.json"
        first = load_registry(path)
        second = load_registry(path)  # both read "slot 1 is free"
        claim_slot(first, self._info(1, "/wt-a"), path)
        try:
            claim_slot(second, self._info(1, "/wt-b"), path)
        except SlotClaimedError as e:
            assert "/wt-a" in str(e)
        else:
            raise AssertionError("second claim must be refused")
        assert load_registry(path).slots[1].worktree_path == "/wt-a"

    def test_reclaim_for_same_worktree_is_idempotent(self, tmp_path) -> None:
        path = tmp_path / "registry.json"
        reg = load_registry(path)
        claim_slot(reg, self._info(1, "/wt-a"), path)
        claim_slot(reg, self._info(1, "/wt-a"), path)
        assert load_registry(path).slots[1].worktree_path == "/wt-a"


class TestMutationsNeverEraseConcurrentClaims:
    def _info(self, slot_id: int, wt: str) -> SlotInfo:
        return SlotInfo(
            slot_id=slot_id, project="p", worktree_path=wt, slot_dir="/s",
            compose_file_copy="", ports={}, claimed_at="", status="provisioning",
        )

    def test_status_update_keeps_a_claim_made_after_the_snapshot(
        self, tmp_path
    ) -> None:
        from devops_ai.registry import update_slot_status

        path = tmp_path / "registry.json"
        mine = load_registry(path)
        claim_slot(mine, self._info(1, "/wt-a"), path)
        other = load_registry(path)
        claim_slot(other, self._info(2, "/wt-b"), path)   # after my snapshot
        update_slot_status(mine, 1, "running", path)
        on_disk = load_registry(path)
        assert on_disk.slots[1].status == "running"
        assert 2 in on_disk.slots, "a stale snapshot must not erase slot 2"

    def test_release_keeps_other_entries(self, tmp_path) -> None:
        path = tmp_path / "registry.json"
        mine = load_registry(path)
        claim_slot(mine, self._info(1, "/wt-a"), path)
        other = load_registry(path)
        claim_slot(other, self._info(2, "/wt-b"), path)
        release_slot(mine, 1, path)
        on_disk = load_registry(path)
        assert 1 not in on_disk.slots and 2 in on_disk.slots
