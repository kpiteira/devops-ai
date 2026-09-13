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

import _socket
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
    answer: Callable[[str], tuple[int, str | bytes]] = staticmethod(
        lambda path: kv2(key=VALUE)
    )
    # Declare a longer body than is sent, so the client hits the end of the
    # connection mid-read — the shape a proxy or a killed server produces.
    overstate_length_by: int = 0
    # When set, every answer carries this `Location` header.
    location: str | None = None
    # The raw request lines, before `http.server` normalises `//` to `/`
    # (gh-87389) — the only place a doubled slash is still observable.
    lines: list[str] = field(default_factory=list)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        fake: FakeBao = self.server.fake  # type: ignore[attr-defined]
        fake.asked.append(Asked(self.path, self.headers.get("X-Vault-Token")))
        fake.lines.append(self.requestline)
        status, body = fake.answer(self.path)
        payload = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if fake.location is not None:
            self.send_header("Location", fake.location)
        self.send_header(
            "Content-Length", str(len(payload) + fake.overstate_length_by)
        )
        self.end_headers()
        self.wfile.write(payload)
        if fake.overstate_length_by:
            self.close_connection = True

    def log_message(self, *args: object) -> None:
        """Silence the stderr access log."""


@pytest.fixture(autouse=True)
def _connections_allowed_here(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo, for this file only, the unit suite's process-wide connect guard.

    `tests/unit/conftest.py` replaces `socket.socket.connect` at import time, so
    it governs whatever else is collected in the same pytest session — these
    tests fail under `pytest tests/unit tests/integration` for a reason that has
    nothing to do with them. Put the inherited C method back per test;
    monkeypatch restores the guard afterwards, so the unit suite keeps it.
    """
    monkeypatch.setattr(socket.socket, "connect", _socket.socket.connect)


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
        """Asserted on the raw request line: `self.path` has already been
        normalised by `http.server`, so it stays green with the trim removed —
        a real OpenBao would instead answer the doubled path with a redirect.
        """
        read("bao://kv/app#key", BAO_ADDR=bao.addr + "/", BAO_TOKEN="t-1")

        assert bao.lines[0] == "GET /v1/kv/data/app HTTP/1.1"

    def test_path_segments_are_escaped_not_interpolated(self, bao: FakeBao) -> None:
        """A path is a path: it cannot smuggle a query string onto the URL.

        Without `quote()` the server sees `/v1/kv/data/a b?list=true`, so the
        `?list=true` becomes a query the reference never asked for.
        """
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

        with pytest.raises(SecretResolutionError, match="bao login") as raised:
            read("bao://kv/a#key", VAULT_ADDR=bao.addr, VAULT_TOKEN="t")

        # The token may have come from either spelling or from the file, and a
        # refusal is remedied the same way whichever it was — so name both
        # rather than the one the reader happens not to use.
        message = str(raised.value)
        assert "BAO_TOKEN" in message and "VAULT_TOKEN" in message

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

    def test_a_status_error_does_not_leave_the_response_open(
        self, bao: FakeBao
    ) -> None:
        """`HTTPError` is the response; `raise ... from None` still chains it.

        `__suppress_context__` hides the chain from a traceback but keeps
        `__context__`, and `resolve_all` holds every error it collected — so an
        unclosed response stays open for as long as the caller holds the list.
        Measured before `exc.close()`: 5 of 5 collected errors held an open one.
        """
        bao.answer = lambda path: (403, "{}")

        with pytest.raises(SecretResolutionError) as raised:
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        node: BaseException | None = raised.value
        responses = []
        while node is not None:
            fp = getattr(node, "fp", None)
            if fp is not None:
                responses.append(fp)
            node = node.__context__
        assert responses, "the HTTPError must still be reachable to be checked"
        assert all(fp.closed for fp in responses)

    def test_the_json_failure_names_the_variable_that_was_used(
        self, bao: FakeBao
    ) -> None:
        """`VAULT_ADDR` is a supported spelling; guidance naming `BAO_ADDR`
        sends the user to a variable they never set."""
        bao.answer = lambda path: (200, "<html>a proxy login page</html>")

        with pytest.raises(SecretResolutionError, match="VAULT_ADDR") as raised:
            read("bao://kv/a#key", VAULT_ADDR=bao.addr, VAULT_TOKEN="t")

        assert "BAO_ADDR" not in str(raised.value)

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

    def test_a_body_that_is_not_utf8_is_a_sentence_not_a_decode_crash(
        self, bao: FakeBao
    ) -> None:
        """A secret is bytes; the answer carrying it need not decode.

        Observed escaping as `UnicodeDecodeError` while the handler below
        caught only `json.JSONDecodeError`.
        """
        bao.answer = lambda path: (200, b'{"data": {"data": {"key": "\xff\xfe"}}}')

        with pytest.raises(SecretResolutionError, match="did not answer with JSON"):
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

    def test_a_body_cut_short_is_a_connection_failure_not_a_crash(
        self, bao: FakeBao
    ) -> None:
        """IncompleteRead is an HTTPException, not an OSError — easy to miss.

        Observed escaping as `http.client.IncompleteRead` while the handler
        below caught only `(URLError, OSError)`.
        """
        bao.overstate_length_by = 5000

        with pytest.raises(SecretResolutionError, match="Cannot reach"):
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


# --- The token goes only where the user pointed it ---


class TestRedirects:
    def test_a_redirect_to_another_host_is_refused_not_followed(
        self, bao: FakeBao, tmp_path: Path
    ) -> None:
        """urllib copies headers onto the redirected request.

        Measured before the custom handler: the second server received
        `X-Vault-Token` and its value was returned as the secret.
        """
        elsewhere = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        other = FakeBao(addr=f"http://127.0.0.1:{elsewhere.server_address[1]}")
        other.answer = lambda path: kv2(key="value-from-the-other-host")
        elsewhere.fake = other  # type: ignore[attr-defined]
        thread = threading.Thread(
            target=elsewhere.serve_forever, kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        thread.start()
        bao.answer = lambda path: (301, "")
        bao.location = other.addr + "/v1/kv/data/a"

        try:
            with pytest.raises(SecretResolutionError, match="different host") as e:
                read("bao://kv/a#key", VAULT_ADDR=bao.addr, VAULT_TOKEN="s3cret")
            assert other.asked == [], "the token must not reach another server"
            assert "VAULT_ADDR" in str(e.value), "guidance names the spelling used"
            assert "BAO_ADDR" not in str(e.value)
        finally:
            elsewhere.shutdown()
            elsewhere.server_close()
            thread.join(timeout=5)

    @pytest.mark.parametrize(
        ("case", "location"),
        [("no location header", None), ("a loop back to itself", "/v1/kv/data/a")],
    )
    def test_a_redirect_with_no_cross_host_hop_reports_an_unfollowable_redirect(
        self, bao: FakeBao, case: str, location: str | None
    ) -> None:
        """A bare 30x means three different things, and two are not a hop.

        Measured before the handler recorded whether it refused anything: a 302
        with no `Location`, and a 302 looping to the same path, both came back
        as "redirected to a different host" — a sentence about the one cause
        that was not true in either case.
        """
        bao.answer = lambda path: (302, "")
        bao.location = location

        with pytest.raises(SecretResolutionError) as raised:
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        message = str(raised.value)
        assert "could not be followed" in message, case
        assert "different host" not in message, case

    def test_an_upgrade_to_another_scheme_is_not_called_a_different_host(
        self, bao: FakeBao
    ) -> None:
        """The canonical http-to-https redirect is the same host, not another.

        It is still refused — the token went out over the configured scheme
        before this answer arrived, and following the redirect would not undo
        that — but the message must say what happened. Measured before the
        split: an `https://` Location on the same host and port came back as
        "redirected to a different host".
        """
        bao.answer = lambda path: (301, "")
        host = bao.addr.split("//", 1)[1]
        bao.location = f"https://{host}/v1/kv/data/a"

        with pytest.raises(SecretResolutionError) as raised:
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        message = str(raised.value)
        assert "another scheme" in message
        assert "different host" not in message
        assert bao.addr in message, "the address the token did go to is named"

    def test_a_redirect_on_the_same_server_is_followed(self, bao: FakeBao) -> None:
        """A server cleaning up its own path must still resolve."""
        def answer(path: str) -> tuple[int, str | bytes]:
            if path == "/v1/kv/data/a":
                return 301, ""
            return kv2(key=VALUE)

        bao.answer = answer
        bao.location = "/v1/kv/data/moved"

        assert read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t") == VALUE
        assert [a.path for a in bao.asked] == [
            "/v1/kv/data/a", "/v1/kv/data/moved"
        ]


# --- The token goes only to the named server, by every route ---


class TestAmbientProxies:
    def test_an_http_proxy_in_the_environment_never_sees_the_token(
        self, bao: FakeBao, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`build_opener` installs a default `ProxyHandler` unless given one.

        Measured before the empty handler: the proxy received
        `GET http://…/v1/kv/data/a` carrying `X-Vault-Token`, and the vault
        server received nothing at all. `getproxies()` reads `os.environ`, not
        the resolve context, so the variables are set there — and the no-proxy
        variables are cleared, because `ProxyHandler` consults those before
        using a proxy at all. Both servers are on `127.0.0.1`, so an inherited
        `no_proxy=localhost,127.0.0.1` would send the request straight to the
        vault with the empty handler removed, and this check would then pass
        while proving nothing.
        """
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        seen = FakeBao(addr=f"http://127.0.0.1:{proxy.server_address[1]}")
        proxy.fake = seen  # type: ignore[attr-defined]
        thread = threading.Thread(
            target=proxy.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        for name in ("NO_PROXY", "no_proxy"):
            monkeypatch.delenv(name, raising=False)
        for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(name, seen.addr)

        try:
            got = read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="s3cret-token")

            assert got == VALUE
            assert seen.asked == [], "the proxy must never see the request"
            assert bao.asked[0].token == "s3cret-token"
        finally:
            proxy.shutdown()
            proxy.server_close()
            thread.join(timeout=5)


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
        """The one path where the token really does enter an exception.

        `http.client.putheader` refuses a header value with a line break and
        puts the value in its `ValueError` — verified: the text reads
        ``Invalid header value b's3cret\ntoken'``. The provider rejects such a
        token before the request is built, so that exception never happens; if
        anyone lets it through and reports `{exc}`, this goes red.
        """
        with pytest.raises(SecretResolutionError) as raised:
            read(
                "bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="s3cret\ntoken"
            )

        message = str(raised.value)
        assert "s3cret" not in message and "line break" in message
        assert bao.asked == [], "a token that cannot be sent must not be sent"

    def test_a_403_says_nothing_it_was_not_told(self, bao: FakeBao) -> None:
        """The refusal message is a constant template — characterisation only."""
        bao.answer = lambda path: (403, json.dumps({"errors": [SIBLING]}))

        with pytest.raises(SecretResolutionError) as raised:
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        assert SIBLING not in str(raised.value)
