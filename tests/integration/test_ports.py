"""Integration tests for port availability (requires real socket binding)."""

from __future__ import annotations

import socket

from devops_ai.ports import check_ports_available


class TestCheckPortsAvailable:
    def test_all_free(self) -> None:
        # Use high ports unlikely to be in use
        ports = {"PORT_A": 59871, "PORT_B": 59872}
        conflicts = check_ports_available(ports)
        assert conflicts == []

    def test_conflict_detected(self) -> None:
        # Bind + listen so port is truly occupied (SO_REUSEADDR on Linux
        # allows rebinding without listen)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 59873))
        sock.listen(1)
        try:
            ports = {"BUSY_PORT": 59873, "FREE_PORT": 59874}
            conflicts = check_ports_available(ports)
            assert len(conflicts) == 1
            assert conflicts[0].port == 59873
            assert conflicts[0].env_var == "BUSY_PORT"
            assert isinstance(conflicts[0].message, str)
        finally:
            sock.close()
