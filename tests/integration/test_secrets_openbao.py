"""The OpenBao provider against a real HTTP server rather than a patched one.

The provider's whole job is a conversation, so these tests hold up the other end
of it: a threaded `http.server` that records what was asked and answers what the
case needs answered. That covers what a dev-mode container cannot be made to
produce on demand — a 500, a sealed server, a mount that is not KV v2, a refused
connection — while the acceptance suite proves the happy path against a real
OpenBao.

Integration, not unit: a loopback socket is real I/O, which `tests/unit` forbids.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from devops_ai.secrets import ResolveContext, SecretResolutionError, resolve

VALUE = "the-value"
SIBLING = "the-sibling-value"


def kv2(**data: object) -> tuple[int, str]:
    """The envelope a KV v2 read returns."""
    return 200, json.dumps({"data": {"data": data, "metadata": {"version": 1}}})


@dataclass
class Asked:
    path: str
    token: str | None


@dataclass
class FakeBao:
    addr: str
    asked: list[Asked] = field(default_factory=list)
    answer: Callable[[str], tuple[int, str]] = staticmethod(
        lambda path: kv2(key=VALUE)
    )


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        fake: FakeBao = self.server.fake  # type: ignore[attr-defined]
        fake.asked.append(Asked(self.path, self.headers.get("X-Vault-Token")))
        status, body = fake.answer(self.path)
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        """Silence the stderr access log."""


@pytest.fixture()
def bao() -> Iterator[FakeBao]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    fake = FakeBao(addr=f"http://127.0.0.1:{server.server_address[1]}")
    server.fake = fake  # type: ignore[attr-defined]
    # A short poll interval: `shutdown()` waits for one, and the default half
    # second would be most of this file's runtime.
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield fake
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def read(ref: str, **env: str) -> str:
    return resolve("K", ref, ResolveContext(env=env))


# --- The request the provider makes ---


class TestTheRequest:
    def test_reads_the_named_key_through_the_kv2_data_path(
        self, bao: FakeBao
    ) -> None:
        bao.answer = lambda path: kv2(token=VALUE, other=SIBLING)

        got = read(
            "bao://kv/homelab/lux/grafana#token",
            BAO_ADDR=bao.addr,
            BAO_TOKEN="t-1",
        )

        assert got == VALUE
        assert bao.asked == [Asked("/v1/kv/data/homelab/lux/grafana", "t-1")]

    def test_a_trailing_slash_on_the_address_does_not_double_up(
        self, bao: FakeBao
    ) -> None:
        read("bao://kv/app#key", BAO_ADDR=bao.addr + "/", BAO_TOKEN="t-1")

        assert bao.asked[0].path == "/v1/kv/data/app"

    def test_path_segments_are_escaped_not_interpolated(self, bao: FakeBao) -> None:
        """A path is a path: it cannot smuggle a query string onto the URL."""
        read("bao://kv/a b?list=true#key", BAO_ADDR=bao.addr, BAO_TOKEN="t-1")

        assert bao.asked[0].path == "/v1/kv/data/a%20b%3Flist%3Dtrue"

    def test_a_non_string_value_is_rendered_as_it_was_stored(
        self, bao: FakeBao
    ) -> None:
        bao.answer = lambda path: kv2(port=8200, enabled=True)

        assert read("bao://kv/a#port", BAO_ADDR=bao.addr, BAO_TOKEN="t") == "8200"
        assert read("bao://kv/a#enabled", BAO_ADDR=bao.addr, BAO_TOKEN="t") == "true"

    def test_a_malformed_reference_never_reaches_the_network(
        self, bao: FakeBao
    ) -> None:
        with pytest.raises(SecretResolutionError):
            read("bao://kv/app", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        assert bao.asked == []


# --- Where and who ---


class TestAddressAndToken:
    def test_bao_addr_wins_over_vault_addr(self, bao: FakeBao) -> None:
        got = read(
            "bao://kv/a#key",
            BAO_ADDR=bao.addr,
            VAULT_ADDR="http://127.0.0.1:1",
            BAO_TOKEN="t",
        )
        assert got == VALUE

    def test_vault_addr_alone_is_honored(self, bao: FakeBao) -> None:
        assert read("bao://kv/a#key", VAULT_ADDR=bao.addr, VAULT_TOKEN="t") == VALUE

    def test_a_blank_address_counts_as_absent(self, bao: FakeBao) -> None:
        got = read(
            "bao://kv/a#key", BAO_ADDR="  ", VAULT_ADDR=bao.addr, BAO_TOKEN="t"
        )
        assert got == VALUE

    def test_bao_token_wins_over_vault_token(self, bao: FakeBao) -> None:
        read(
            "bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="right", VAULT_TOKEN="wrong"
        )

        assert bao.asked[0].token == "right"

    def test_the_token_file_under_the_context_home_is_the_last_resort(
        self, bao: FakeBao, tmp_path: Path
    ) -> None:
        """kinfra resolves in an environment it built, not the process's own."""
        (tmp_path / ".vault-token").write_text("from-the-file\n")

        read("bao://kv/a#key", BAO_ADDR=bao.addr, HOME=str(tmp_path))

        assert bao.asked[0].token == "from-the-file", "whitespace must be stripped"


# --- What the server says, and what the user is told ---


class TestServerFailures:
    def test_a_refused_connection_names_the_address(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            dead = f"http://127.0.0.1:{probe.getsockname()[1]}"

        with pytest.raises(SecretResolutionError, match=dead):
            read("bao://kv/a#key", BAO_ADDR=dead, BAO_TOKEN="t")

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_token_says_how_to_log_in(
        self, bao: FakeBao, status: int
    ) -> None:
        bao.answer = lambda path: (status, '{"errors":["permission denied"]}')

        with pytest.raises(SecretResolutionError, match="bao login"):
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

    def test_a_missing_secret_points_at_the_mount_and_path(
        self, bao: FakeBao
    ) -> None:
        bao.answer = lambda path: (404, '{"errors":[]}')

        with pytest.raises(SecretResolutionError, match="kv/homelab/absent"):
            read("bao://kv/homelab/absent#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

    def test_a_sealed_server_is_named_as_such(self, bao: FakeBao) -> None:
        bao.answer = lambda path: (503, '{"errors":["Vault is sealed"]}')

        with pytest.raises(SecretResolutionError, match="sealed"):
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

    def test_an_unexpected_status_reports_the_code_and_not_the_body(
        self, bao: FakeBao
    ) -> None:
        bao.answer = lambda path: (500, json.dumps({"leaked": VALUE}))

        with pytest.raises(SecretResolutionError) as raised:
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        assert "500" in str(raised.value)
        assert VALUE not in str(raised.value)

    def test_an_answer_that_is_not_json_blames_the_address(
        self, bao: FakeBao
    ) -> None:
        bao.answer = lambda path: (200, "<html>a proxy login page</html>")

        with pytest.raises(SecretResolutionError, match="BAO_ADDR"):
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

    def test_a_kv_v1_shaped_answer_says_the_mount_is_wrong(
        self, bao: FakeBao
    ) -> None:
        """KV v1 has no nested `data`; it is out of scope, so say so clearly."""
        bao.answer = lambda path: (200, json.dumps({"data": {"key": VALUE}}))

        with pytest.raises(SecretResolutionError, match="KV v2 mount"):
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

    def test_a_deleted_current_version_is_not_an_empty_secret(
        self, bao: FakeBao
    ) -> None:
        bao.answer = lambda path: (
            200,
            json.dumps({"data": {"data": None, "metadata": {"destroyed": True}}}),
        )

        with pytest.raises(SecretResolutionError, match="current version"):
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")


# --- The no-leak invariant ---


class TestNothingLeaks:
    def test_a_missing_key_is_named_and_its_siblings_are_not(
        self, bao: FakeBao
    ) -> None:
        bao.answer = lambda path: kv2(token=VALUE, other=SIBLING)

        with pytest.raises(SecretResolutionError) as raised:
            read("bao://kv/a#absent", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        message = str(raised.value)
        assert "absent" in message
        assert VALUE not in message and SIBLING not in message

    def test_the_token_never_appears_in_a_failure(self, bao: FakeBao) -> None:
        bao.answer = lambda path: (403, "{}")

        with pytest.raises(SecretResolutionError) as raised:
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="s3cret-token")

        assert "s3cret-token" not in str(raised.value)
