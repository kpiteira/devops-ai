"""The Azure Key Vault provider, exercised through the resolver's public surface.

No patching: `az` is replaced at the seam that is actually slow and non-deterministic
— the subprocess — by a real executable on the PATH the provider is given. Everything
between `resolve()` and that boundary is the shipped code.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from devops_ai.secrets import (
    ERROR,
    OK,
    ResolveContext,
    SecretResolutionError,
    check,
    provider_for,
    resolve,
    schemes,
)

REF = "akv://a-vault/a-secret"
ARGV_LOG = "argv.json"


def fake_az(
    directory: Path, *, stdout: str = "", stderr: str = "", code: int = 0
) -> Path:
    """An `az` on `directory` that records its argv and answers as told."""
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "az"
    log = directory / ARGV_LOG
    program.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(log)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        # Bytes, not text: what a vault returns is UTF-8 whatever the child's
        # locale would have encoded it as, and a test about encodings must not
        # route its own fixture through one.
        f"sys.stdout.buffer.write({stdout!r}.encode('utf-8'))\n"
        f"sys.stderr.buffer.write({stderr!r}.encode('utf-8'))\n"
        f"sys.exit({code})\n",
        encoding="utf-8",
    )
    program.chmod(0o755)
    return log


def slow_az(directory: Path, seconds: float) -> None:
    """An `az` that never answers in time."""
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "az"
    program.write_text(f"#!{sys.executable}\nimport time\ntime.sleep({seconds})\n")
    program.chmod(0o755)


def context(directory: Path) -> ResolveContext:
    return ResolveContext(base_dir=directory, env={"PATH": str(directory / "bin")})


def recorded(log: Path) -> list[str]:
    return list(json.loads(log.read_text()))


def azure_error(text: str) -> str:
    """az's own shape: an ERROR: line, and nothing structured beyond it."""
    return f"ERROR: {text}\n"


# --- The scheme is a provider ---


class TestDiscovery:
    def test_the_scheme_is_claimed_by_a_provider(self) -> None:
        assert "akv://" in schemes()
        assert provider_for(REF) is not None

    def test_a_reference_with_nothing_after_the_scheme_is_not_a_literal(self) -> None:
        """A typo must surface as a malformed reference, never resolve to itself."""
        assert provider_for("akv://") is not None


# --- Reading ---


class TestReadingASecret:
    def test_returns_the_value_az_reports(self, tmp_path: Path) -> None:
        fake_az(tmp_path / "bin", stdout=json.dumps("the-value"))
        assert resolve("K", REF, context(tmp_path)) == "the-value"

    def test_a_value_keeps_its_exact_bytes(self, tmp_path: Path) -> None:
        """Tabs, embedded newlines and a trailing newline survive — a PEM key does.

        This is what JSON output buys over TSV, whose row terminator is
        indistinguishable from a value's own trailing newline.
        """
        value = "line1\tTABBED\nline2\n"
        fake_az(tmp_path / "bin", stdout=json.dumps(value))
        assert resolve("K", REF, context(tmp_path)) == value

    def test_a_non_ascii_value_is_returned_intact(self, tmp_path: Path) -> None:
        """The UTF-8 bytes a vault returns decode to the value, not to mojibake.

        `ensure_ascii=False` is load-bearing: with `json.dumps`'s default the fake
        `az` would emit `\\u` escapes, pure ASCII, and this would pass under any
        codec at all. It still cannot claim the *locale* boundary — the process
        locale is fixed at interpreter start, so only a child process can cross it.
        `tests/integration/test_secret_locale.py` is where that lives.
        """
        value = "café-über"
        fake_az(tmp_path / "bin", stdout=json.dumps(value, ensure_ascii=False))
        assert resolve("K", REF, context(tmp_path)) == value

    def test_a_bare_reference_pins_no_version(self, tmp_path: Path) -> None:
        log = fake_az(tmp_path / "bin", stdout=json.dumps("v"))
        resolve("K", REF, context(tmp_path))
        argv = recorded(log)
        assert "--version" not in argv
        assert argv[argv.index("--vault-name") + 1] == "a-vault"
        assert argv[argv.index("--name") + 1] == "a-secret"

    def test_a_versioned_reference_pins_that_version(self, tmp_path: Path) -> None:
        log = fake_az(tmp_path / "bin", stdout=json.dumps("v"))
        resolve("K", f"{REF}/abc123", context(tmp_path))
        argv = recorded(log)
        assert argv[argv.index("--version") + 1] == "abc123"
        assert argv[argv.index("--name") + 1] == "a-secret"

    def test_the_value_never_reaches_the_child_argv(self, tmp_path: Path) -> None:
        """The invariant, guarded where a future refactor could break it."""
        log = fake_az(tmp_path / "bin", stdout=json.dumps("the-value"))
        resolve("K", REF, context(tmp_path))
        assert not any("the-value" in arg for arg in recorded(log))

    def test_check_reports_ok_without_the_value(self, tmp_path: Path) -> None:
        fake_az(tmp_path / "bin", stdout=json.dumps("the-value"))
        result = check("K", REF, context(tmp_path))
        assert (result.status, result.reason) == (OK, None)
        assert "the-value" not in result.format()


# --- Malformed references ---


class TestMalformedReferences:
    @pytest.mark.parametrize(
        "ref",
        ["akv://", "akv://a-vault", "akv://a-vault/", "akv:///a-secret",
         "akv://a-vault/a-secret/", "akv://a-vault/a-secret/v/extra"],
    )
    def test_are_rejected_with_the_expected_shape(
        self, ref: str, tmp_path: Path
    ) -> None:
        fake_az(tmp_path / "bin", stdout=json.dumps("unused"))
        with pytest.raises(SecretResolutionError, match="Malformed reference"):
            resolve("K", ref, context(tmp_path))


# --- Failures az reports ---


class TestAzureCliFailures:
    """Classified from stderr text: `secret show` exits 3 for a missing secret."""

    def test_a_missing_secret_says_not_found_and_names_the_reference(
        self, tmp_path: Path
    ) -> None:
        fake_az(
            tmp_path / "bin",
            code=3,
            stderr=azure_error(
                "(SecretNotFound) A secret with (name/id) a-secret was not found "
                "in this key vault."
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
        assert "not found" in caught.value.message.lower()
        assert REF in caught.value.message

    def test_not_logged_in_says_how_to_log_in(self, tmp_path: Path) -> None:
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error("Please run 'az login' to setup account."),
        )
        with pytest.raises(SecretResolutionError, match="az login"):
            resolve("K", REF, context(tmp_path))

    def test_access_denied_names_the_role_to_ask_for(self, tmp_path: Path) -> None:
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(Forbidden) Caller is not authorized to perform action on "
                "resource."
            ),
        )
        with pytest.raises(SecretResolutionError, match="Key Vault Secrets User"):
            resolve("K", REF, context(tmp_path))

    def test_access_denied_relays_azs_own_words(self, tmp_path: Path) -> None:
        """Forbidden covers unrelated states; az's reason must survive the guess."""
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error("(Forbidden) Client address is not authorized."),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
        assert "Client address is not authorized" in caught.value.message

    def test_a_disabled_secret_is_not_reported_as_a_permissions_problem(
        self, tmp_path: Path
    ) -> None:
        """az's real answer for a disabled secret, captured from the vault.

        It arrives as `(Forbidden)`; sending the operator to chase an RBAC role
        for a secret they disabled themselves is a confident wrong answer.
        """
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(Forbidden) Operation get is not allowed on a disabled secret."
            )
            + 'Code: Forbidden\nInner error: {\n "code": "SecretDisabled"\n}\n',
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
        message = caught.value.message
        assert "disabled" in message
        assert "Key Vault Secrets User" not in message
        assert "a-secret/<version>" in message, "the workaround must be offered"

    def test_an_unreachable_vault_points_at_the_vault_name(
        self, tmp_path: Path
    ) -> None:
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error("Failed to resolve 'a-vault.vault.azure.net'"),
        )
        with pytest.raises(SecretResolutionError, match="could not be reached"):
            resolve("K", REF, context(tmp_path))

    def test_a_vault_named_forbidden_is_still_diagnosed_as_unreachable(
        self, tmp_path: Path
    ) -> None:
        """Classification anchors on Azure's codes, not on names containing them.

        Vault and secret names are chosen by the caller and reach stderr verbatim
        — az echoes the host it failed to resolve — so a bare substring scan lets
        a legal name impersonate an error code and hide the real diagnosis.
        """
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error("Failed to resolve 'forbidden.vault.azure.net'"),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", "akv://forbidden/a-secret", context(tmp_path))
        message = caught.value.message
        assert "could not be reached" in message
        assert "Key Vault Secrets User" not in message, "a name is not a code"

    def test_a_secret_named_secretnotfound_behind_a_denial_says_denied(
        self, tmp_path: Path
    ) -> None:
        """The same confusion the other way: the code outranks the name."""
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(Forbidden) Caller is not authorized to perform action on "
                "https://a-vault.vault.azure.net/secrets/secretnotfound."
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", "akv://a-vault/secretnotfound", context(tmp_path))
        message = caught.value.message
        assert "Key Vault Secrets User" in message
        assert "not found" not in message.lower(), "a name is not a code"

    def test_a_secret_named_like_a_code_is_not_diagnosed_as_that_code(
        self, tmp_path: Path
    ) -> None:
        """Where the earlier code anchoring still leaked: an *invalid* name.

        `(Forbidden)` is not a legal Key Vault name, which is the point — az
        rejects it with `BadParameter` and echoes it into the message, where a
        scan for `(forbidden)` found it and reported a denial. Codes are read
        only from the fields az writes codes in, so the echo is inert.
        """
        name = "(Forbidden)"
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                f"(BadParameter) The request URI contains an invalid name: {name}"
            )
            + "Code: BadParameter\n",
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"akv://a-vault/{name}", context(tmp_path))
        message = caught.value.message
        assert "Key Vault Secrets User" not in message, "an echoed name is not a code"
        assert "invalid name" in message

    def test_an_unclassified_failure_quotes_azs_error_line(
        self, tmp_path: Path
    ) -> None:
        fake_az(
            tmp_path / "bin", code=7, stderr=azure_error("something unexpected")
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
        assert "something unexpected" in caught.value.message
        assert "exit status 7" in caught.value.message

    def test_a_silent_failure_says_how_to_see_azs_output(
        self, tmp_path: Path
    ) -> None:
        """A red with nothing to read is not a diagnosis — name the next command."""
        fake_az(tmp_path / "bin", code=1, stderr="")
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
        assert "az keyvault secret show" in caught.value.message
        assert "a-vault" in caught.value.message

    def test_a_silent_failure_on_a_pinned_version_suggests_that_version(
        self, tmp_path: Path
    ) -> None:
        """Diagnosing the current version when a pinned one failed misleads.

        The current version can be healthy while the pinned one is missing or
        disabled; that retry succeeds and proves the wrong thing.
        """
        fake_az(tmp_path / "bin", code=1, stderr="")
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"{REF}/abc123", context(tmp_path))
        assert "--version abc123" in caught.value.message

    def test_the_suggested_retry_does_not_print_the_secret(
        self, tmp_path: Path
    ) -> None:
        """`az keyvault secret show` prints the value in its default JSON.

        Guidance that puts a secret on the operator's screen — and into shell
        history and CI logs — is the leak this module refuses everywhere else.
        """
        fake_az(tmp_path / "bin", code=1, stderr="")
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
        message = caught.value.message
        assert "--output none" in message
        # The other half of the version rule: an unpinned reference must not
        # grow a `--version None`, which the pinned test alone cannot catch.
        assert "--version" not in message

    def test_an_unclassified_failure_quotes_nothing_but_error_lines(
        self, tmp_path: Path
    ) -> None:
        """Only az's own ERROR: lines are relayed; other chatter is dropped."""
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr="WARNING: noisy detail\n" + azure_error("the real problem"),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
        assert "the real problem" in caught.value.message
        assert "noisy detail" not in caught.value.message

    def test_output_that_is_not_json_is_reported_not_returned(
        self, tmp_path: Path
    ) -> None:
        fake_az(tmp_path / "bin", stdout="not json at all")
        with pytest.raises(SecretResolutionError, match="not JSON"):
            resolve("K", REF, context(tmp_path))

    def test_a_secret_without_a_value_is_an_error_not_the_string_none(
        self, tmp_path: Path
    ) -> None:
        fake_az(tmp_path / "bin", stdout="null\n")
        with pytest.raises(SecretResolutionError, match="no value"):
            resolve("K", REF, context(tmp_path))

    def test_an_az_that_never_answers_is_reported_as_a_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one branch no canned answer can reach — the child must really hang.

        The timeout itself is shortened; everything else, including the kill, is
        the shipped path.
        """
        from devops_ai.secrets.providers import azurekeyvault

        monkeypatch.setattr(azurekeyvault, "TIMEOUT", 0.3)
        slow_az(tmp_path / "bin", seconds=10)
        with pytest.raises(SecretResolutionError, match="timed out"):
            resolve("K", REF, context(tmp_path))

    def test_a_version_that_is_not_a_version_id_says_so(
        self, tmp_path: Path
    ) -> None:
        """az's real answer to `akv://v/s/latest`, captured from the vault.

        Key Vault reads a non-id path segment as an operation name, so its reply
        never mentions versions at all.
        """
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(BadParameter) Method GET does not allow operation 'latest'"
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"{REF}/latest", context(tmp_path))
        message = caught.value.message
        assert "latest is not a version id" in message
        assert "list-versions" in message

    def test_an_invalid_secret_name_is_not_blamed_on_the_version(
        self, tmp_path: Path
    ) -> None:
        """az's real answer to a name Azure will not accept, captured from the vault.

        `_parse` takes any non-empty segment, so BadParameter arrives for bad
        *names* too. Blaming the version would bury it under advice to list the
        versions of a name Azure has already rejected.
        """
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(BadParameter) The request URI contains an invalid name: bad_name"
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", "akv://a-vault/bad_name/abc123", context(tmp_path))
        message = caught.value.message
        assert "invalid name: bad_name" in message, "az's own reason must survive"
        assert "version id" not in message
        assert "list-versions" not in message

    def test_a_name_that_impersonates_the_operation_text_still_reads_truthfully(
        self, tmp_path: Path
    ) -> None:
        """The anchor names *this* version, so echoed text cannot claim the branch.

        az echoes the rejected name verbatim, and the name is the caller's — the
        same opening the error-code anchoring closed for `forbidden`.
        """
        version = "zz99"
        # The collision has to name *this* version. An earlier version of this
        # test spelled a different one, so the anchor could not have matched
        # either way and the test passed without exercising anything.
        impostor = f"does not allow operation '{version}'"
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                f"(BadParameter) The request URI contains an invalid name: {impostor}"
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"akv://a-vault/{impostor}/{version}", context(tmp_path))
        message = caught.value.message
        assert "version id" not in message
        assert "list-versions" not in message
        assert "invalid name" in message, "az's real reason must survive"

    def test_bad_parameter_without_a_pinned_version_is_not_blamed_on_one(
        self, tmp_path: Path
    ) -> None:
        """The branch is gated: a bare reference has no version to accuse."""
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error("(BadParameter) something else entirely"),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
        assert "version id" not in caught.value.message
        assert "something else entirely" in caught.value.message

    def test_check_reports_the_failure_as_error(self, tmp_path: Path) -> None:
        fake_az(
            tmp_path / "bin", code=3, stderr=azure_error("(SecretNotFound) gone")
        )
        assert check("K", REF, context(tmp_path)).status == ERROR


class TestSuggestedCommandsAreSafeToPaste:
    """Guidance this module tells a human to run is built, not interpolated.

    A reference is not always the operator's own typing — a committed
    `[sandbox.secrets]` entry is one too — and `_parse` accepts any non-empty
    segment. The property under test is what a *shell* would make of the
    suggested command, so the assertions parse it with `shlex.split` rather
    than looking for quote characters.
    """

    # Slash-free on purpose: `_parse` splits on "/", so a payload containing one
    # is rejected as malformed long before it reaches any guidance. That is not a
    # defence — `$(id)` and `;whoami` need no slash at all.
    #
    # The spaces are load-bearing for the *test*, not the attack: `shlex.split`
    # tokenizes, it does not evaluate, so a payload with no space comes back as
    # one token whether or not it was ever quoted, and the assertion below could
    # not fail. With spaces, unquoted guidance tokenizes into several arguments
    # and the test goes red — which is the only reason it is worth running.
    HOSTILE = "$(id) ; whoami"

    def test_a_hostile_segment_stays_one_literal_argument_in_the_retry(
        self, tmp_path: Path
    ) -> None:
        fake_az(tmp_path / "bin", code=1, stderr="")
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"akv://a-vault/{self.HOSTILE}", context(tmp_path))
        command = caught.value.message.split("run: ", 1)[1]
        assert shlex.split(command) == [
            "az", "keyvault", "secret", "show",
            "--vault-name", "a-vault", "--name", self.HOSTILE,
            "--output", "none",
        ], "a shell would run the segment instead of passing it"

    def test_a_hostile_segment_stays_one_literal_argument_in_list_versions(
        self, tmp_path: Path
    ) -> None:
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(BadParameter) Method GET does not allow operation 'latest'"
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"akv://a-vault/{self.HOSTILE}/latest", context(tmp_path))
        command = caught.value.message.split("take an id from: ", 1)[1]
        assert shlex.split(command) == [
            "az", "keyvault", "secret", "list-versions",
            "--vault-name", "a-vault", "--name", self.HOSTILE,
        ]

    def test_a_segment_carrying_a_single_quote_still_survives_whole(
        self, tmp_path: Path
    ) -> None:
        """The case that separates real quoting from a wrapper in quotes.

        `shlex.join` encloses in single quotes, so an embedded `'` has to be
        broken out and re-escaped. A hand-rolled `f"'{segment}'"` renders this
        payload as three shell words and passes every other test in this class.
        """
        payload = "it's $(id); rm -rf ~"
        fake_az(tmp_path / "bin", code=1, stderr="")
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"akv://a-vault/{payload}", context(tmp_path))
        command = caught.value.message.split("run: ", 1)[1]
        assert shlex.split(command) == [
            "az", "keyvault", "secret", "show",
            "--vault-name", "a-vault", "--name", payload,
            "--output", "none",
        ]

    def test_an_ordinary_name_is_not_dressed_up_in_quotes(
        self, tmp_path: Path
    ) -> None:
        """Quoting must not make the message a real failure prints any uglier."""
        fake_az(tmp_path / "bin", code=1, stderr="")
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"{REF}/abc123", context(tmp_path))
        assert (
            "az keyvault secret show --vault-name a-vault --name a-secret "
            "--version abc123 --output none"
        ) in caught.value.message


# --- The tool is found on the PATH the child will use ---


class TestAzIsFoundOnThePathTheChildWillUse:
    def test_an_az_only_on_the_context_path_is_found_and_run(
        self, tmp_path: Path
    ) -> None:
        fake_az(tmp_path / "bin", stdout=json.dumps("from-the-context-path"))
        assert resolve("K", REF, context(tmp_path)) == "from-the-context-path"

    def test_a_context_without_a_path_falls_back_to_the_system_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """os.defpath is what exec falls back to; discovery must use it too."""
        fake_az(tmp_path / "defbin", stdout=json.dumps("from-the-default-path"))
        monkeypatch.setattr(os, "defpath", str(tmp_path / "defbin"))
        ctx = ResolveContext(base_dir=tmp_path, env={})
        assert resolve("K", REF, ctx) == "from-the-default-path"

    def test_an_az_on_no_searched_path_reports_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Isolated: whether the machine has a real `az` is not this test's business."""
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(os, "defpath", str(empty))
        ctx = ResolveContext(base_dir=tmp_path, env={})
        with pytest.raises(SecretResolutionError, match="Azure CLI .az. not found"):
            resolve("K", REF, ctx)
