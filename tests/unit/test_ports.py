"""Unit tests for port allocator (pure computation only)."""

from __future__ import annotations

from devops_ai.config import InfraConfig, ServicePort
from devops_ai.ports import (
    check_base_port_safety,
    compute_ports,
)


def _config_with_ports(*ports: tuple[str, int]) -> InfraConfig:
    """Helper: create InfraConfig with given (env_var, base_port) pairs."""
    return InfraConfig(
        project_name="test-project",
        prefix="test",
        has_sandbox=True,
        ports=[ServicePort(env_var=e, base_port=p) for e, p in ports],
    )


class TestComputePorts:
    def test_simple(self) -> None:
        config = _config_with_ports(("API_PORT", 8080))
        result = compute_ports(config, slot_id=1)
        assert result == {"API_PORT": 8081}

    def test_multiple(self) -> None:
        config = _config_with_ports(
            ("API_PORT", 8080),
            ("DB_PORT", 5432),
            ("WORKER_PORT", 5003),
        )
        result = compute_ports(config, slot_id=3)
        assert result == {"API_PORT": 8083, "DB_PORT": 5435, "WORKER_PORT": 5006}

    def test_slot_100(self) -> None:
        config = _config_with_ports(("API_PORT", 8080), ("HIGH_PORT", 65400))
        result = compute_ports(config, slot_id=100)
        assert result == {"API_PORT": 8180, "HIGH_PORT": 65500}
        # All ports must be valid (< 65536)
        for port in result.values():
            assert port < 65536


class TestBasePortSafety:
    def test_warning_proximity(self) -> None:
        """Two projects with base ports 1 apart → warning."""
        config = _config_with_ports(("API_PORT", 8080))
        other_entries = [
            {"project": "other-project", "ports": {"OTHER_PORT": 8081}},
        ]
        warnings = check_base_port_safety(config, other_entries)
        assert len(warnings) >= 1
        assert "other-project" in warnings[0]

    def test_ok_far_apart(self) -> None:
        """Two projects with base ports 1000 apart → no warning."""
        config = _config_with_ports(("API_PORT", 8080))
        other_entries = [
            {"project": "other-project", "ports": {"OTHER_PORT": 9080}},
        ]
        warnings = check_base_port_safety(config, other_entries)
        assert warnings == []
