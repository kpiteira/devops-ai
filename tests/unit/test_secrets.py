"""Tests for the secret reference resolver and its providers.

No patching: a ResolveContext carries the environment and the base directory, so
every case here runs the real code against a real directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from devops_ai.secrets import (
    ERROR,
    LITERAL,
    OK,
    ResolveContext,
    SecretResolutionError,
    check,
    layered_env,
    parse_env_file,
    provider_for,
    resolve,
    resolve_all,
    schemes,
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "\n"
        "PLAIN=plain-value\n"
        'DOUBLE="double-value"\n'
        "SINGLE='single-value'\n"
        "export EXPORTED=exported-value\n"
        "  SPACED  =  spaced-value  \n"
        "WITH_EQUALS=a=b=c\n"
        "EMPTY=\n"
        "not-an-assignment\n"
    )
    return tmp_path


def ctx(base: Path, **env: str) -> ResolveContext:
    return ResolveContext(base_dir=base, env=env)


# --- The KEY=value format ---


class TestEnvFileFormat:
    def test_parses_every_accepted_line_shape(self, project: Path) -> None:
        values = parse_env_file((project / ".env").read_text())
        assert values == {
            "PLAIN": "plain-value",
            "DOUBLE": "double-value",
            "SINGLE": "single-value",
            "EXPORTED": "exported-value",
            "SPACED": "spaced-value",
            "WITH_EQUALS": "a=b=c",
            "EMPTY": "",
        }

    def test_a_hash_inside_a_value_is_not_a_comment(self) -> None:
        assert parse_env_file("TOKEN=abc#def") == {"TOKEN": "abc#def"}

    def test_mismatched_quotes_are_left_alone(self) -> None:
        assert parse_env_file("K=\"half'") == {"K": "\"half'"}

    def test_later_lines_win(self) -> None:
        assert parse_env_file("K=first\nK=second\n") == {"K": "second"}


# --- Host environment, with the .env fallback ---


class TestHostEnvironment:
    def test_exported_variable_wins_over_the_file(self, project: Path) -> None:
        context = ctx(project, PLAIN="from-shell")
        assert resolve("K", "$PLAIN", context) == "from-shell"
        assert resolve("K", "env://PLAIN", context) == "from-shell"

    def test_falls_back_to_the_env_file(self, project: Path) -> None:
        context = ctx(project)
        assert resolve("K", "$PLAIN", context) == "plain-value"
        assert resolve("K", "env://PLAIN", context) == "plain-value"

    def test_missing_everywhere_names_the_variable(self, project: Path) -> None:
        with pytest.raises(SecretResolutionError) as exc:
            resolve("MY_KEY", "$ABSENT", ctx(project))
        assert "ABSENT" in exc.value.message
        assert exc.value.message.startswith("MY_KEY: ")
        assert "not set" in exc.value.message

    def test_missing_fallback_file_is_not_an_error_by_itself(
        self, tmp_path: Path
    ) -> None:
        assert resolve("K", "$PRESENT", ctx(tmp_path, PRESENT="v")) == "v"
        with pytest.raises(SecretResolutionError, match="not set"):
            resolve("K", "$ABSENT", ctx(tmp_path))

    def test_the_scheme_is_claimed_even_when_malformed(self, project: Path) -> None:
        """A typo must not resolve to itself — that is how a scheme is claimed."""
        assert provider_for("env://") is not None
        with pytest.raises(SecretResolutionError, match="Malformed"):
            resolve("K", "env://", ctx(project))

    def test_a_bare_dollar_is_a_literal(self, project: Path) -> None:
        assert resolve("K", "$", ctx(project)) == "$"
        assert provider_for("$") is None


# --- A key in a named file ---


class TestDotenvReference:
    def test_reads_the_named_key(self, project: Path) -> None:
        assert resolve("K", "dotenv://.env#SINGLE", ctx(project)) == "single-value"

    def test_path_is_relative_to_the_base_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "config"
        nested.mkdir()
        (nested / "prod.env").write_text("TOKEN=nested-token\n")
        assert (
            resolve("K", "dotenv://config/prod.env#TOKEN", ctx(tmp_path))
            == "nested-token"
        )

    def test_absolute_paths_are_left_alone(self, tmp_path: Path) -> None:
        target = tmp_path / "abs.env"
        target.write_text("TOKEN=absolute-token\n")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        assert (
            resolve("K", f"dotenv://{target}#TOKEN", ctx(elsewhere))
            == "absolute-token"
        )

    def test_missing_key_names_the_key_and_the_file(self, project: Path) -> None:
        with pytest.raises(SecretResolutionError) as exc:
            resolve("K", "dotenv://.env#ABSENT", ctx(project))
        assert "ABSENT" in exc.value.message and ".env" in exc.value.message

    def test_missing_file_names_the_file(self, project: Path) -> None:
        with pytest.raises(SecretResolutionError, match="not found"):
            resolve("K", "dotenv://nope.env#KEY", ctx(project))

    def test_a_reference_without_a_key_is_malformed(self, project: Path) -> None:
        with pytest.raises(SecretResolutionError, match="Malformed"):
            resolve("K", "dotenv://.env", ctx(project))


# --- OpenBao / Vault references, before any socket is opened ---


class TestOpenBaoReferenceShape:
    """Everything the provider settles without asking a server.

    Reaching a server is `tests/integration/test_secrets_openbao.py`; what a
    malformed reference or an unusable environment means is decided here, where
    it is decided in the code.
    """

    # A syntactically valid address that is never reached: every case here
    # fails before a socket is opened, which `tests/unit/conftest.py` enforces.
    ADDRESS = "http://127.0.0.1:1"

    @pytest.mark.parametrize(
        "ref",
        [
            "bao://kv/app",  # no #key
            "bao://kv/app#",  # empty key
            "bao://kv#key",  # no path under the mount
            "bao://#key",  # no mount
            "bao://",
        ],
    )
    def test_a_reference_that_is_not_mount_path_key_says_so(self, ref: str) -> None:
        with pytest.raises(SecretResolutionError, match="<mount>/<path>"):
            resolve("K", ref, ResolveContext(env={"BAO_ADDR": self.ADDRESS,
                                                  "BAO_TOKEN": "t"}))

    def test_no_address_anywhere_names_both_variables(self) -> None:
        with pytest.raises(SecretResolutionError, match="BAO_ADDR.*VAULT_ADDR"):
            resolve("K", "bao://kv/a#key", ResolveContext(env={"BAO_TOKEN": "t"}))

    def test_an_address_that_is_not_a_web_url_is_refused(
        self, tmp_path: Path
    ) -> None:
        """urlopen speaks `file:` too: a typo must not read a path back as a secret."""
        planted = tmp_path / "passwd"
        planted.write_text("root:x:0:0")

        with pytest.raises(SecretResolutionError, match="http or https"):
            resolve(
                "K",
                "bao://kv/a#key",
                ResolveContext(env={"BAO_ADDR": planted.as_uri(), "BAO_TOKEN": "t"}),
            )

    @pytest.mark.parametrize(
        ("here", "there", "same"),
        [
            ("https://vault/x", "https://vault:443/y", True),
            ("http://vault/x", "http://vault:80/y", True),
            ("https://vault/x", "https://VAULT/y", True),
            ("https://vault:8200/x", "https://vault/y", False),
            ("https://vault/x", "https://other/y", False),
            # An explicit `:0` is a port, and `_address` refuses it outright —
            # normalising it to the default here would let a redirect reach
            # what a configured address may not.
            ("http://vault/x", "http://vault:0/y", False),
        ],
    )
    def test_a_default_port_is_the_same_endpoint_written_twice(
        self, here: str, there: str, same: bool
    ) -> None:
        """Tested on the helper because a test cannot bind :443.

        The behaviour that uses it — a redirect to another host, to another
        port, or to another scheme — is covered end to end in
        `tests/integration/test_secrets_openbao.py`. Only this equivalence
        needs a privileged port to stage, so it is asserted where it is
        decided: comparing raw `netloc` made `https://vault:443` and
        `https://vault` different servers, and refused the redirect between
        them.
        """
        from devops_ai.secrets.providers.openbao import _origin

        assert (_origin(here) == _origin(there)) is same

    @pytest.mark.parametrize("address", ["ftp://vault.example.com", "gopher://v/1"])
    def test_a_scheme_urlopen_speaks_but_openbao_does_not_is_refused(
        self, address: str
    ) -> None:
        """The sibling `file://` case names the scheme rule but does not isolate
        it: `file://` has no host either, so `bool(parts.hostname)` refuses it
        with the scheme check removed. These do have a host, so only the scheme
        check stands between them and urllib opening an FTP connection.
        """
        context = ResolveContext(env={"BAO_ADDR": address, "BAO_TOKEN": "t"})
        with pytest.raises(SecretResolutionError, match="http or https"):
            resolve("K", "bao://kv/a#key", context)

    @pytest.mark.parametrize(
        "address",
        [
            "http://[::1",  # urlsplit raises "Invalid IPv6 URL" on this
            "https://vault.example.com?wrapped=1",
            "https://vault.example.com#fragment",
            "vault.example.com:8200",  # no scheme at all
        ],
    )
    def test_an_address_that_is_not_a_plain_base_url_is_refused(
        self, address: str
    ) -> None:
        """A fragment silently eats the whole path: the request would GET `/`."""
        context = ResolveContext(env={"BAO_ADDR": address, "BAO_TOKEN": "t"})
        with pytest.raises(SecretResolutionError, match="not a server address"):
            resolve("K", "bao://kv/a#key", context)

    @pytest.mark.parametrize(
        "address",
        [
            "https://user:hunter2@vault.example.com",
            "https://hunter2@vault.example.com",
        ],
    )
    def test_an_address_carrying_credentials_is_refused_without_echoing_it(
        self, address: str
    ) -> None:
        """`netloc` keeps userinfo, and the address is named in every sentence below.

        A password in `BAO_ADDR` would ride into stderr on the first connection
        failure — the one thing this module promises never to print.
        """
        context = ResolveContext(env={"BAO_ADDR": address, "BAO_TOKEN": "t"})
        with pytest.raises(SecretResolutionError) as exc:
            resolve("K", "bao://kv/a#key", context)
        assert "not a server address" in exc.value.message
        assert "hunter2" not in exc.value.message

    @pytest.mark.parametrize(
        "address",
        [
            "http://127.0.0.1:99999",
            "http://127.0.0.1:-1",
            "http://127.0.0.1:abc",
            "http://127.0.0.1:0",
        ],
    )
    def test_an_address_whose_port_is_not_a_port_is_refused_as_an_address(
        self, address: str
    ) -> None:
        """Unvalidated, `:99999` reaches `getaddrinfo` and answers as a name failure.

        `_address` is the function whose job is saying what a bad address is;
        a port outside 0-65535 is one, and `.port` parses only on access.
        Port 0 is the bind-any port and never a destination: unrefused it
        answers `[Errno 49] Can't assign requested address`, which is about
        this machine rather than about the address the user typed.
        """
        context = ResolveContext(env={"BAO_ADDR": address, "BAO_TOKEN": "t"})
        with pytest.raises(SecretResolutionError, match="not a server address"):
            resolve("K", "bao://kv/a#key", context)

    @pytest.mark.parametrize("address", ["http://:8200", "https://:443"])
    def test_an_address_that_names_no_host_is_refused(self, address: str) -> None:
        """A `netloc` of `:8200` is non-empty and its port parses — but `hostname`
        is None, and urllib reads the empty host as localhost. A typo'd address
        would present the token to a server the address never named.
        """
        context = ResolveContext(env={"BAO_ADDR": address, "BAO_TOKEN": "t"})
        with pytest.raises(SecretResolutionError, match="not a server address"):
            resolve("K", "bao://kv/a#key", context)

    @pytest.mark.skipif(
        getattr(os, "geteuid", lambda: 1)() == 0,
        reason="root reads through mode 000",
    )
    def test_a_token_file_under_an_unreadable_home_says_so(
        self, tmp_path: Path
    ) -> None:
        """`Path.exists()` propagates EACCES — the existence check was the traceback.

        Only ENOENT/ENOTDIR/EBADF/ELOOP are swallowed by `exists()`; a home the
        user cannot stat into raised `PermissionError` straight out of `resolve`.
        """
        home = tmp_path / "home"
        home.mkdir()
        (home / ".vault-token").write_text("hvs.token\n")
        home.chmod(0o000)
        try:
            context = ResolveContext(
                env={"BAO_ADDR": self.ADDRESS, "HOME": str(home)}
            )
            with pytest.raises(SecretResolutionError, match="Cannot read"):
                resolve("K", "bao://kv/a#key", context)
        finally:
            home.chmod(0o755)

    @pytest.mark.parametrize("ref", ["bao://kv/../secret/a#key", "bao://kv/./a#key"])
    def test_a_path_that_climbs_out_of_its_mount_is_refused(self, ref: str) -> None:
        """The server would clean the path and redirect outside the mount."""
        context = ResolveContext(env={"BAO_ADDR": self.ADDRESS, "BAO_TOKEN": "t"})
        with pytest.raises(SecretResolutionError, match="<mount>/<path>"):
            resolve("K", ref, context)

    @pytest.mark.parametrize(
        ("token", "why"),
        [("s3cret\ntoken", "a line break"), ("s3cret-\u4e2d", "outside latin-1")],
    )
    def test_a_token_an_http_header_cannot_carry_is_refused_by_name(
        self, token: str, why: str
    ) -> None:
        """`http.client` would refuse both — with the value in its message.

        And that message is a `ValueError`/`UnicodeEncodeError`, which
        `_read_secret` catches as "the server did not answer with JSON" — a
        sentence about a request that was never sent.
        """
        context = ResolveContext(env={"BAO_ADDR": self.ADDRESS, "BAO_TOKEN": token})
        with pytest.raises(SecretResolutionError) as exc:
            resolve("K", "bao://kv/a#key", context)
        assert "BAO_TOKEN" in exc.value.message, why
        assert "cannot be sent" in exc.value.message
        assert "s3cret" not in exc.value.message

    def test_an_undecodable_token_file_says_how_it_is_malformed(
        self, tmp_path: Path
    ) -> None:
        """The wording `envfile` settled on, not `.reason`'s "invalid start byte"."""
        (tmp_path / ".vault-token").write_bytes(b"hvs.\xff\xfe\n")

        context = ResolveContext(
            env={"BAO_ADDR": self.ADDRESS, "HOME": str(tmp_path)}
        )
        with pytest.raises(SecretResolutionError, match="not valid UTF-8 text"):
            resolve("K", "bao://kv/a#key", context)

    def test_an_unreadable_token_file_is_not_reported_as_no_token(
        self, tmp_path: Path
    ) -> None:
        """Two causes, two messages: `bao login` only helps once you know which."""
        (tmp_path / ".vault-token").write_bytes(b"hvs.\xff\xfe\n")

        context = ResolveContext(
            env={"BAO_ADDR": self.ADDRESS, "HOME": str(tmp_path)}
        )
        with pytest.raises(SecretResolutionError, match="Cannot read"):
            resolve("K", "bao://kv/a#key", context)

    def test_a_ca_bundle_that_is_not_there_is_named(self, tmp_path: Path) -> None:
        context = ResolveContext(
            env={
                "BAO_ADDR": self.ADDRESS,
                "BAO_TOKEN": "t",
                "BAO_CACERT": str(tmp_path / "absent.pem"),
            }
        )
        with pytest.raises(SecretResolutionError, match="BAO_CACERT"):
            resolve("K", "bao://kv/a#key", context)

    def test_no_token_anywhere_says_how_to_get_one(self, tmp_path: Path) -> None:
        context = ResolveContext(
            env={"BAO_ADDR": self.ADDRESS, "HOME": str(tmp_path / "nowhere")}
        )
        with pytest.raises(SecretResolutionError, match="bao login"):
            resolve("K", "bao://kv/a#key", context)

    def test_a_context_with_no_home_reads_no_token_file_at_all(self) -> None:
        """The home is the context's, and there is no fallback to the process's.

        `Path.home()` would consult `os.environ`, making this the one input the
        provider does not take from `ctx.env` — so a deliberately sanitised
        context could still read the operator's `~/.vault-token`. Every real
        caller carries HOME, so only such a context sees this.
        """
        context = ResolveContext(env={"BAO_ADDR": self.ADDRESS})
        with pytest.raises(SecretResolutionError, match="bao login") as exc:
            resolve("K", "bao://kv/a#key", context)
        assert "which writes" not in exc.value.message, "no file was looked for"

    def test_an_empty_token_file_is_no_token_at_all(self, tmp_path: Path) -> None:
        (tmp_path / ".vault-token").write_text("\n")

        context = ResolveContext(
            env={"BAO_ADDR": self.ADDRESS, "HOME": str(tmp_path)}
        )
        with pytest.raises(SecretResolutionError, match="bao login"):
            resolve("K", "bao://kv/a#key", context)


# --- Literals and unregistered schemes ---


class TestLiterals:
    @pytest.mark.parametrize(
        "value",
        ["plain-text", "", "postgres://dev:dev@db:5432/app", "weird://not/registered"],
    )
    def test_unclaimed_references_resolve_to_themselves(
        self, value: str, project: Path
    ) -> None:
        assert provider_for(value) is None
        assert resolve("K", value, ctx(project)) == value


class TestUnreadableFiles:
    """Every caller promises an actionable message, so nothing may escape as a crash."""

    def test_non_utf8_file_is_an_os_error_not_a_decode_crash(
        self, tmp_path: Path
    ) -> None:
        bad = tmp_path / "binary.env"
        bad.write_bytes(b"KEY=\xff\xfe not text\n")

        with pytest.raises(SecretResolutionError) as exc:
            resolve("K", "dotenv://binary.env#KEY", ctx(tmp_path))
        assert "binary.env" in exc.value.message
        assert "UTF-8" in exc.value.message

    def test_utf8_is_read_as_utf8_whatever_the_locale_says(
        self, tmp_path: Path
    ) -> None:
        """The reader promises UTF-8; the locale default is not a promise."""
        (tmp_path / ".env").write_bytes("K=caf\u00e9-\u00fcber\n".encode())
        assert resolve("K", "dotenv://.env#K", ctx(tmp_path)) == "caf\u00e9-\u00fcber"

    def test_the_env_fallback_survives_an_undecodable_dotenv(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".env").write_bytes(b"K=\xff\xfe\n")
        with pytest.raises(SecretResolutionError, match="UTF-8"):
            resolve("K", "$ABSENT", ctx(tmp_path))


class TestTheToolIsFoundOnThePathTheChildWillUse:
    """Discovery and exec must agree: the child resolves on ctx.env's PATH."""

    @staticmethod
    def _fake_op(directory: Path, value: str) -> None:
        program = directory / "op"
        program.write_text(f'#!/bin/sh\nprintf %s {value!r}\n')
        program.chmod(0o755)

    def test_a_tool_only_on_the_context_path_is_found_and_run(
        self, tmp_path: Path
    ) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        self._fake_op(bin_dir, "value-from-the-context-path")

        context = ResolveContext(base_dir=tmp_path, env={"PATH": str(bin_dir)})
        assert (
            resolve("K", "op://v/i/f", context) == "value-from-the-context-path"
        ), "the provider searched a different PATH than the child would use"

    def test_a_context_without_a_path_falls_back_to_the_system_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """os.defpath is what exec falls back to; discovery must use it too."""
        bin_dir = tmp_path / "defbin"
        bin_dir.mkdir()
        self._fake_op(bin_dir, "value-from-the-default-path")
        monkeypatch.setattr(os, "defpath", str(bin_dir))

        context = ResolveContext(base_dir=tmp_path, env={})
        assert resolve("K", "op://v/i/f", context) == "value-from-the-default-path"

    def test_a_tool_on_no_searched_path_reports_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Isolated: whether /bin holds `op` is not this test's business."""
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(os, "defpath", str(empty))

        context = ResolveContext(base_dir=tmp_path, env={})
        with pytest.raises(SecretResolutionError, match="not found"):
            resolve("K", "op://v/i/f", context)


# --- Discovery ---


class TestDiscovery:
    def test_every_milestone_scheme_has_a_provider(self) -> None:
        assert {"env://", "dotenv://", "op://", "bao://"} <= set(schemes())

    def test_each_reference_is_claimed_by_exactly_one_provider(self) -> None:
        for ref in ("env://A", "$A", "dotenv://f#A", "op://v/i/f", "bao://m/p#k"):
            assert provider_for(ref) is not None


# --- Resolving a set of references ---


class TestResolveAll:
    def test_collects_every_failure_and_keeps_the_successes(
        self, project: Path
    ) -> None:
        resolved, errors = resolve_all(
            {
                "GOOD": "dotenv://.env#PLAIN",
                "LIT": "just-text",
                "BAD": "dotenv://.env#ABSENT",
                "WORSE": "$ABSENT",
            },
            ctx(project),
        )
        assert resolved == {"GOOD": "plain-value", "LIT": "just-text"}
        assert {e.var_name for e in errors} == {"BAD", "WORSE"}
        assert all(e.message.startswith(f"{e.var_name}: ") for e in errors)

    def test_no_value_leaks_into_an_error_message(self, project: Path) -> None:
        _, errors = resolve_all({"BAD": "dotenv://.env#ABSENT"}, ctx(project))
        assert "plain-value" not in errors[0].message


# --- Classification, without values ---


class TestCheck:
    def test_classifies_ok_literal_and_error(self, project: Path) -> None:
        context = ctx(project)
        results = [
            check("A", "dotenv://.env#PLAIN", context),
            check("C", "literal-c", context),
            check("U", "weird://not/registered", context),
            check("BAD", "dotenv://.env#ABSENT", context),
        ]
        assert [r.status for r in results] == [OK, LITERAL, LITERAL, ERROR]
        assert all("plain-value" not in r.format() for r in results)

    def test_an_error_line_carries_the_reason_once(self, project: Path) -> None:
        line = check("BAD", "dotenv://.env#ABSENT", ctx(project)).format()
        assert line.startswith("BAD: error — ")
        assert "ABSENT" in line
        assert line.count("BAD") == 1, f"the key is a column, not a prefix: {line}"

    def test_the_stderr_form_of_the_same_failure_is_labelled(
        self, project: Path
    ) -> None:
        with pytest.raises(SecretResolutionError) as exc:
            resolve("BAD", "dotenv://.env#ABSENT", ctx(project))
        assert exc.value.message == f"BAD: {exc.value.reason}"

    def test_an_ok_line_is_just_the_status(self, project: Path) -> None:
        assert check("A", "dotenv://.env#PLAIN", ctx(project)).format() == "A: ok"


class TestTheEnvironmentEntriesResolveIn:
    """Literal entries are declarations, so they beat whatever the shell exported.

    One definition, used by `ksecret run`, `ksecret check`, `check --infra` and
    kinfra's `[sandbox.secrets]` — they must not drift.
    """

    def test_a_literal_line_overrides_the_parent_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OP_ACCOUNT", "stale-from-the-shell")
        environ = layered_env({"OP_ACCOUNT": "declared.1password.com"})
        assert environ["OP_ACCOUNT"] == "declared.1password.com"

    def test_the_parent_environment_still_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNRELATED", "from-the-shell")
        assert layered_env({"K": "literal"})["UNRELATED"] == "from-the-shell"

    def test_references_are_not_placed_before_they_resolve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("A", raising=False)
        assert "A" not in layered_env({"A": "dotenv://.env#A"})
