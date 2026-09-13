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
import ssl
import subprocess
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from devops_ai.secrets import (
    ProviderError,
    ResolveContext,
    SecretResolutionError,
    resolve,
    write,
)

VALUE = "the-value"
SIBLING = "the-sibling-value"
# Every status `_status_error` claims as a redirect.
# Every 3xx the provider must refuse, including the two urllib would never
# have offered `redirect_request` (300, 304): the code tests a range, and an
# enumeration here would only ever confirm the enumeration.
REDIRECT_CODES = (300, 301, 302, 303, 304, 307, 308)


def kv2(**data: object) -> tuple[int, str]:
    """The envelope a KV v2 read returns."""
    return 200, json.dumps({"data": {"data": data, "metadata": {"version": 1}}})


@dataclass
class Asked:
    path: str
    token: str | None
    method: str = "GET"
    content_type: str | None = None
    body: dict | None = None


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
        self._serve()

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        self._serve()

    def do_PATCH(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        self._serve()

    def _serve(self) -> None:
        fake: FakeBao = self.server.fake  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        fake.asked.append(
            Asked(
                self.path,
                self.headers.get("X-Vault-Token"),
                self.command,
                self.headers.get("Content-Type"),
                json.loads(raw) if raw else None,
            )
        )
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


def store(ref: str, value: str, **env: str) -> str:
    return write(ref, value, ResolveContext(env=env))


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

    def test_a_json_escape_for_a_lone_surrogate_is_refused_not_returned(
        self, bao: FakeBao
    ) -> None:
        """A `\\uD800` escape is the one way this provider invents a surrogate.

        The body arrives as ASCII and decodes fine; `json.loads` is what turns
        the escape into a lone surrogate. Returned unchanged it would reach
        `encode_env`, whose `surrogateescape` hands the child a raw byte
        instead of the value's UTF-8 — a different secret than the vault holds,
        with nothing raised. Refused in `resolver._representable`, which every
        provider's value passes through, so the class is closed in one place
        rather than once per provider that happens to parse JSON.
        """
        body = "recognisable-secret-body"
        bao.answer = lambda path: kv2(key=f"\ud800{body}")

        with pytest.raises(SecretResolutionError, match="unpaired surrogate") as caught:
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        assert body not in caught.value.message
        assert "d800" not in caught.value.message.lower(), "not even as an escape"

    def test_a_paired_surrogate_escape_is_an_ordinary_character(
        self, bao: FakeBao
    ) -> None:
        """The control: refusing every `\\u`-escaped astral character would
        satisfy the test above just as well, and break real secrets."""
        bao.answer = lambda path: kv2(key="grin-\U0001f600")

        got = read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        assert got == "grin-\U0001f600"

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
        # rather than the one the reader happens not to use. Same for the
        # command: a Vault-only install has no `bao` binary to run.
        message = str(raised.value)
        assert "BAO_TOKEN" in message and "VAULT_TOKEN" in message
        assert "bao login" in message and "vault login" in message

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
        """`null` is the shape KV v2 defines for a deleted current version."""
        bao.answer = lambda path: (
            200,
            json.dumps({"data": {"data": None, "metadata": {"destroyed": True}}}),
        )

        with pytest.raises(SecretResolutionError, match="current version"):
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

    @pytest.mark.parametrize("payload", [["a", "b"], "text", 7])
    def test_a_malformed_payload_is_not_called_a_deleted_version(
        self, bao: FakeBao, payload: object
    ) -> None:
        """Only `null` means deleted; anything else non-dict is a bad answer.

        Telling the operator their latest version was destroyed, when the
        server sent a list, is a wrong remediation for someone else's problem.
        """
        bao.answer = lambda path: (200, json.dumps({"data": {"data": payload}}))

        with pytest.raises(SecretResolutionError, match="KV v2 mount") as raised:
            read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="t")

        assert "deleted" not in str(raised.value)


# --- The token goes only where the user pointed it ---


class TestRedirects:
    """No redirect is followed, whatever it names (Karl's call, 2026-09-13).

    The provider used to follow a redirect that stayed on the configured
    server. Deciding per hop whether a location may be handed a vault token is
    attack surface out of proportion to reading one secret, so every 3xx is now
    an error naming its status.
    """

    @pytest.mark.parametrize("code", REDIRECT_CODES)
    @pytest.mark.parametrize(
        ("case", "location"),
        [
            ("same path, another host", "http://127.0.0.1:9/v1/kv/data/a"),
            ("same server, another path", "/v1/kv/data/moved"),
            ("same host, another scheme", "https://127.0.0.1:8200/v1/kv/data/a"),
            ("the default port spelled out", "http://127.0.0.1:80/v1/kv/data/a"),
            ("a loop back to itself", "/v1/kv/data/a"),
            ("no location header at all", None),
        ],
    )
    def test_every_redirect_is_refused(
        self, bao: FakeBao, code: int, case: str, location: str | None
    ) -> None:
        """Including the two that used to be followed.

        "same server, another path" and "the default port spelled out" both
        resolved before this change; they are refusals now, which is the point
        of it. The message names the status and the address variable to fix.
        """
        bao.answer = lambda path: (code, "")
        bao.location = location

        with pytest.raises(SecretResolutionError) as raised:
            read("bao://kv/a#key", VAULT_ADDR=bao.addr, VAULT_TOKEN="t")

        message = str(raised.value)
        assert "redirect" in message, case
        assert str(code) in message, case
        assert "VAULT_ADDR" in message, "the spelling that was actually set"
        assert len(bao.asked) == 1, f"{case}: the hop must not be taken"

    def test_the_token_never_reaches_a_redirect_target(
        self, bao: FakeBao
    ) -> None:
        """urllib copies request headers onto the redirected request.

        Measured while redirects were followed: the second server received
        `X-Vault-Token` and its answer came back as the secret. Nothing may
        reach it now.
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
            with pytest.raises(SecretResolutionError, match="redirect") as e:
                read("bao://kv/a#key", BAO_ADDR=bao.addr, BAO_TOKEN="s3cret-token")
            assert other.asked == [], "the token must not reach another server"
            assert "BAO_ADDR" in str(e.value)
            assert "s3cret-token" not in str(e.value)
        finally:
            elsewhere.shutdown()
            elsewhere.server_close()
            thread.join(timeout=5)


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


# --- The private-CA path, over real TLS ---


@pytest.fixture(scope="module")
def private_ca(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway self-signed certificate for 127.0.0.1, and its own CA.

    `openssl` rather than a library: the package declares no runtime or test
    dependency for this, and the binary is present on macOS and on the CI image.
    """
    directory = tmp_path_factory.mktemp("ca")
    cert, key = directory / "cert.pem", directory / "key.pem"
    try:
        made = subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
                "-days", "1", "-nodes", "-keyout", str(key), "-out", str(cert),
                "-subj", "/CN=127.0.0.1", "-addext",
                "subjectAltName=IP:127.0.0.1",
            ],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        pytest.skip("openssl is not installed; it is not a declared dependency")
    if made.returncode != 0:
        pytest.skip(f"openssl could not make a test certificate: {made.stderr[-200:]}")
    return directory


@pytest.fixture()
def tls_bao(private_ca: Path) -> Iterator[FakeBao]:
    """The fake server again, behind TLS signed by that certificate."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # The default leaves TLS 1.0/1.1 reachable, which the security gate flags —
    # rightly, even in a fixture: this stands in for a real server.
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        certfile=private_ca / "cert.pem", keyfile=private_ca / "key.pem"
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    fake = FakeBao(addr=f"https://127.0.0.1:{server.server_address[1]}")
    server.fake = fake  # type: ignore[attr-defined]
    server.socket = context.wrap_socket(server.socket, server_side=True)
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


class TestPrivateCertificateAuthority:
    """The homelab deployment the feature exists for, exercised rather than claimed.

    Until these, dropping `HTTPSHandler(context=tls)` from the opener left the
    whole suite green — measured — so `BAO_CACERT` was a documented feature with
    nothing standing behind it.
    """

    @pytest.mark.parametrize("variable", ["BAO_CACERT", "VAULT_CACERT"])
    def test_a_bundle_named_by_either_variable_verifies_the_server(
        self, tls_bao: FakeBao, private_ca: Path, variable: str
    ) -> None:
        env = {"BAO_ADDR": tls_bao.addr, "BAO_TOKEN": "t",
               variable: str(private_ca / "cert.pem")}

        assert resolve("K", "bao://kv/a#key", ResolveContext(env=env)) == VALUE
        assert tls_bao.asked[0].token == "t", "over TLS, and the token arrived"

    def test_without_the_bundle_the_certificate_is_not_trusted(
        self, tls_bao: FakeBao
    ) -> None:
        """The system trust store is the default, and it must really apply.

        If this passed, the CA test above would prove nothing: a suite that
        connects either way cannot tell a configured trust store from no
        verification at all.
        """
        with pytest.raises(SecretResolutionError, match="Cannot reach") as raised:
            read("bao://kv/a#key", BAO_ADDR=tls_bao.addr, BAO_TOKEN="t")

        assert "certificate verify failed" in str(raised.value).lower()
        assert tls_bao.asked == [], "the request must not have been made"

    def test_a_bundle_that_does_not_verify_this_server_is_refused(
        self, tls_bao: FakeBao, tmp_path: Path
    ) -> None:
        """A real bundle, but the wrong one — not a missing-file check."""
        other = tmp_path / "other-ca.pem"
        subprocess.run(  # openssl proven present by `private_ca`
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
             "-days", "1", "-nodes", "-keyout", str(tmp_path / "k.pem"),
             "-out", str(other), "-subj", "/CN=somewhere-else"],
            capture_output=True, text=True, check=True,
        )

        with pytest.raises(SecretResolutionError, match="Cannot reach"):
            read(
                "bao://kv/a#key", BAO_ADDR=tls_bao.addr, BAO_TOKEN="t",
                BAO_CACERT=str(other),
            )


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


# --- Writing one key without disturbing its siblings ---


class TestWritingAKey:
    """A patch, and what happens when the server will not take one.

    The dev container proves the happy path in the acceptance suite; what it
    cannot be made to produce on demand is a 403 on a patch, which is exactly
    the case where getting the fallback wrong would destroy the siblings the
    patch exists to protect.
    """

    def test_a_patch_carries_only_the_named_key_and_the_merge_media_type(
        self, bao: FakeBao
    ) -> None:
        """The media type is not decoration: sent as plain JSON, KV v2 answers
        415 — and a `POST` of the same body would replace every other key."""
        bao.answer = lambda path: (200, "{}")

        got = store(
            "bao://kv/homelab/lux/grafana#token",
            VALUE,
            BAO_ADDR=bao.addr,
            BAO_TOKEN="t-1",
        )

        assert got == "bao://kv/homelab/lux/grafana#token"
        assert bao.asked == [
            Asked(
                "/v1/kv/data/homelab/lux/grafana",
                "t-1",
                "PATCH",
                "application/merge-patch+json",
                {"data": {"token": VALUE}},
            )
        ]

    def test_a_secret_that_does_not_exist_yet_is_created(self, bao: FakeBao) -> None:
        """KV v2 answers 404 to a patch of a secret with no current version."""
        answers = iter([(404, ""), (200, "{}")])
        bao.answer = lambda path: next(answers)

        store("bao://kv/app#token", VALUE, BAO_ADDR=bao.addr, BAO_TOKEN="t-1")

        assert [asked.method for asked in bao.asked] == ["PATCH", "POST"]
        assert bao.asked[1].content_type == "application/json"
        assert bao.asked[1].body == {"data": {"token": VALUE}}

    def test_a_refused_patch_never_falls_back_to_a_replacing_write(
        self, bao: FakeBao
    ) -> None:
        """The one case this file exists for. A token with `update` but not
        `patch` gets a 403, and a `POST` would succeed — by discarding every
        other key in the secret. It is refused with the capability named."""
        bao.answer = lambda path: (403, '{"errors":["permission denied"]}')

        with pytest.raises(ProviderError) as caught:
            store("bao://kv/app#token", VALUE, BAO_ADDR=bao.addr, BAO_TOKEN="t-1")

        assert [asked.method for asked in bao.asked] == ["PATCH"]
        assert "`patch` capability" in str(caught.value)
        assert VALUE not in str(caught.value)

    def test_a_write_refusal_asks_for_write_access_not_read_access(
        self, bao: FakeBao
    ) -> None:
        bao.answer = lambda path: (403, "{}")

        with pytest.raises(ProviderError) as caught:
            store("bao://kv/app#token", VALUE, BAO_ADDR=bao.addr, BAO_TOKEN="t-1")
        write_message = str(caught.value)

        with pytest.raises(SecretResolutionError) as read_caught:
            read("bao://kv/app#token", BAO_ADDR=bao.addr, BAO_TOKEN="t-1")

        assert "read access" in read_caught.value.message
        assert "read access" not in write_message

    def test_a_redirect_is_not_followed_on_the_way_in_either(
        self, bao: FakeBao
    ) -> None:
        """urllib copies the request's headers onto a redirected request, and
        a write's headers carry the token *and* the value."""
        bao.answer = lambda path: (307, "")
        bao.location = "http://127.0.0.1:1/v1/kv/data/app"

        with pytest.raises(ProviderError) as caught:
            store("bao://kv/app#token", VALUE, BAO_ADDR=bao.addr, BAO_TOKEN="t-1")

        assert [asked.method for asked in bao.asked] == ["PATCH"]
        assert "redirect" in str(caught.value)
        assert VALUE not in str(caught.value)

    def test_a_server_that_cannot_be_reached_names_no_value(
        self, bao: FakeBao
    ) -> None:
        with pytest.raises(ProviderError) as caught:
            store(
                "bao://kv/app#token",
                VALUE,
                BAO_ADDR="http://127.0.0.1:1",
                BAO_TOKEN="t-1",
            )

        assert VALUE not in str(caught.value)
        assert "Cannot reach the server" in str(caught.value)

    def test_a_malformed_reference_is_refused_before_anything_is_sent(
        self, bao: FakeBao
    ) -> None:
        with pytest.raises(ProviderError):
            store("bao://kv/app", VALUE, BAO_ADDR=bao.addr, BAO_TOKEN="t-1")

        assert bao.asked == []


class TestWritingOnlyWhenAbsent:
    def test_a_key_that_is_already_there_is_not_patched(self, bao: FakeBao) -> None:
        bao.answer = lambda path: kv2(token="minted-earlier")

        got = write(
            "bao://kv/app#token",
            VALUE,
            ResolveContext(env={"BAO_ADDR": bao.addr, "BAO_TOKEN": "t-1"}),
            if_absent=True,
        )

        assert got == "bao://kv/app#token"
        assert [asked.method for asked in bao.asked] == ["GET"]

    def test_a_sibling_key_is_not_this_key(self, bao: FakeBao) -> None:
        answers = iter([kv2(other="something-else"), (200, "{}")])
        bao.answer = lambda path: next(answers)

        write(
            "bao://kv/app#token",
            VALUE,
            ResolveContext(env={"BAO_ADDR": bao.addr, "BAO_TOKEN": "t-1"}),
            if_absent=True,
        )

        assert [asked.method for asked in bao.asked] == ["GET", "PATCH"]

    def test_a_secret_that_does_not_exist_is_created(self, bao: FakeBao) -> None:
        answers = iter([(404, ""), (404, ""), (200, "{}")])
        bao.answer = lambda path: next(answers)

        write(
            "bao://kv/app#token",
            VALUE,
            ResolveContext(env={"BAO_ADDR": bao.addr, "BAO_TOKEN": "t-1"}),
            if_absent=True,
        )

        assert [asked.method for asked in bao.asked] == ["GET", "PATCH", "POST"]

    def test_a_server_that_could_not_answer_is_not_read_as_room_to_write(
        self, bao: FakeBao
    ) -> None:
        """A refused read is not an absence. Writing on one would be exactly
        the overwrite `--if-absent` was asked to avoid."""
        bao.answer = lambda path: (403, "{}")

        with pytest.raises(ProviderError):
            write(
                "bao://kv/app#token",
                VALUE,
                ResolveContext(env={"BAO_ADDR": bao.addr, "BAO_TOKEN": "t-1"}),
                if_absent=True,
            )

        assert [asked.method for asked in bao.asked] == ["GET"]
