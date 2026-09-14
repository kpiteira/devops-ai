"""The Azure Key Vault provider, exercised through the resolver's public surface.

No patching: `az` is replaced at the seam that is actually slow and non-deterministic
— the subprocess — by a real executable on the PATH the provider is given. Everything
between `resolve()` and that boundary is the shipped code.
"""

from __future__ import annotations

import json
import os
import re
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
from devops_ai.secrets.providers import azurekeyvault

REF = "akv://a-vault/a-secret"
# A Key Vault version id is 32 hexadecimal characters; the provider refuses
# anything else without calling Azure, so tests about *other* things need a
# real-shaped one to get past it.
VERSION = "3a7f1c9e2b4d5068a1c3e5f7092b4d6e"
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
        resolve("K", f"{REF}/{VERSION}", context(tmp_path))
        argv = recorded(log)
        assert argv[argv.index("--version") + 1] == VERSION
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
    def test_a_nul_byte_is_a_malformed_reference_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        """A NUL cannot reach a child process at all.

        `subprocess.run` raises ValueError before `az` starts, and the resolver
        translates only ProviderError — so without this the failure escapes as a
        traceback, and `ksecret check`, whose job is to *report* what resolves,
        crashes instead of reporting.
        """
        fake_az(tmp_path / "bin", stdout=json.dumps("unused"))
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", "akv://a-vault/a\x00b", context(tmp_path))
        message = caught.value.message
        assert "NUL" in message
        assert "\x00" not in message, "the raw byte must not be echoed"

    def test_a_nul_byte_is_reported_by_check_rather_than_raised(
        self, tmp_path: Path
    ) -> None:
        """The contract that broke: `check` classifies, it does not crash."""
        fake_az(tmp_path / "bin", stdout=json.dumps("unused"))
        result = check("K", "akv://a-vault/a\x00b", context(tmp_path))
        assert result.status == ERROR

    # Every separator `str.splitlines()` honours, not just the obvious two —
    # each was confirmed to forge a `Code:` line before the guard existed.
    LINE_SEPARATORS = ["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d",
                       "\x1e", "\x85", "\u2028", "\u2029"]

    @pytest.mark.parametrize("separator", LINE_SEPARATORS)
    def test_a_line_break_cannot_forge_an_azure_code_line(
        self, separator: str, tmp_path: Path
    ) -> None:
        """The hole line-anchoring could not close: a forged line *is* a line.

        az echoes a rejected name, so a segment carrying a separator becomes a
        line of its own in az's output — and `Code: Forbidden` there is read as
        a code. Rejecting the reference is the only place this can be stopped.
        """
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(BadParameter) The request URI contains an invalid name: "
                f"x{separator}Code: Forbidden"
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve(
                "K", f"akv://a-vault/x{separator}Code: Forbidden", context(tmp_path)
            )
        message = caught.value.message
        assert "Malformed reference" in message
        assert "Key Vault Secrets User" not in message, "the forgery still worked"

    def test_an_offending_character_is_shown_escaped_not_echoed(
        self, tmp_path: Path
    ) -> None:
        """A raw line break in the message hides the very thing it is about."""
        fake_az(tmp_path / "bin", stdout=json.dumps("unused"))
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", "akv://a-vault/x\nCode: Forbidden", context(tmp_path))
        message = caught.value.message
        assert "\\n" in message
        assert "\n" not in message.replace("\\n", ""), "a raw break reached the message"

    def test_an_ordinary_reference_is_not_escaped_or_rejected(
        self, tmp_path: Path
    ) -> None:
        """The guard must not touch a reference Azure would accept.

        It used to read `akv://kv-1/café-name`, on the reasoning that an accent
        is legitimate. Key Vault does not store one, so that reference is now
        refused by name — `TestSegmentsAreValidatedBeforeAzIsSpawned` covers it.
        What this still pins is that neither guard fires on an ordinary name.
        """
        fake_az(tmp_path / "bin", stdout=json.dumps("v"))
        assert resolve("K", "akv://kv-1/an-ordinary-name", context(tmp_path)) == "v"

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

    DISABLED_STDERR = (
        "ERROR: (Forbidden) Operation get is not allowed on a disabled secret.\n"
        'Code: Forbidden\nInner error: {\n "code": "SecretDisabled"\n}\n'
    )
    ABSENT_STDERR = (
        "ERROR: (SecretNotFound) A secret with (name/id) a-secret was not found "
        "in this key vault.\nCode: SecretNotFound\n"
    )

    def _read(self, tmp_path: Path, stderr: str, ref: str = REF) -> tuple[int, str]:
        fake_az(tmp_path / "bin", code=1, stderr=stderr)
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", ref, context(tmp_path))
        return 1, caught.value.message

    def test_a_disabled_secret_is_indistinguishable_from_an_absent_one(
        self, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """Karl, 2026-09-13: a disabled secret answers exactly as a missing one.

        Whether a name exists in the vault is not something a caller who cannot
        read it gets to learn, so the assertion is equality of the whole
        message, not the absence of a few words — anything that differs at all
        is a way to tell the two states apart.
        """
        other = tmp_path_factory.mktemp("absent")
        _, disabled = self._read(tmp_path, self.DISABLED_STDERR)
        _, absent = self._read(other, self.ABSENT_STDERR)
        assert disabled == absent
        # Equality on its own would also hold if both had degraded to the same
        # generic failure, so pin what they are equal *to*.
        assert disabled == f"K: Secret not found in Azure Key Vault: {REF}."

    def test_nothing_about_a_disabled_secret_survives_into_the_message(
        self, tmp_path: Path
    ) -> None:
        """The words that would give it away, including az's own relayed line."""
        _, message = self._read(tmp_path, self.DISABLED_STDERR)
        lowered = message.lower()
        for giveaway in ("disabled", "enable", "pin ", "<version>", "forbidden"):
            assert giveaway not in lowered, f"{giveaway!r} discloses the state"
        assert "Key Vault Secrets User" not in message

    def test_a_disabled_pinned_version_answers_the_same_way(
        self, tmp_path: Path
    ) -> None:
        """Disabling is per version, so the pinned read is the other half."""
        _, message = self._read(
            tmp_path, self.DISABLED_STDERR, ref=f"{REF}/{VERSION}"
        )
        assert message == (
            f"K: Secret not found in Azure Key Vault: {REF}/{VERSION}."
        )

    def test_an_unrecognised_denial_never_relays_the_word_disabled(
        self, tmp_path: Path
    ) -> None:
        """The choke point: a shape we could not classify must still not leak.

        If Azure ever reports a disabled secret in a form these anchors miss,
        the Forbidden branch would hand back az's sentence verbatim. `_az_errors`
        drops such a line instead, so the disclosure cannot escape that way.
        """
        _, message = self._read(
            tmp_path,
            "ERROR: (Forbidden) Some new wording about a disabled secret here.\n",
        )
        assert "disabled" not in message.lower()

    def test_an_invalid_name_mentioning_the_state_still_gets_azs_reason(
        self, tmp_path: Path
    ) -> None:
        """Hiding the state must not cost an unrelated diagnosis.

        Azure's invalid-name answer echoes the caller's own text back, which
        discloses nothing about the vault — the caller wrote it. Filtering it
        anyway threw away the real reason.

        `akv://a-vault/disabled secret` was how this arrived before issue #60;
        that reference is refused without a call now, so the echo is put where
        it always actually came from — az's stderr — and the guard is still the
        one under test. Whether Azure can still word an invalid-name reply this
        way is exactly the question `hide_state` must not assume an answer to.
        """
        _, message = self._read(
            tmp_path,
            azure_error(
                "(BadParameter) The request URI contains an invalid name: "
                "disabled secret"
            )
            + "Code: BadParameter\n",
        )
        assert "invalid name: disabled secret" in message

    def test_the_fallback_never_claims_az_was_silent_when_it_was_not(
        self, tmp_path: Path
    ) -> None:
        """The sentence that made the old filter worse than lossy: it lied.

        Dropping az's only ERROR: line left the message asserting that az had
        printed none, which sends the reader looking in the wrong place.
        """
        _, message = self._read(
            tmp_path,
            azure_error(
                "(BadParameter) The request URI contains an invalid name: "
                "disabled secret"
            ),
        )
        # An absence on its own would also hold if the message had changed shape
        # entirely, so pin the line that should have been there all along.
        assert "invalid name: disabled secret" in message
        assert "printed no ERROR" not in message

    def test_a_genuine_permission_denial_still_names_the_role(
        self, tmp_path: Path
    ) -> None:
        """Karl kept this one separate: RBAC still says what to ask for."""
        _, message = self._read(
            tmp_path,
            azure_error(
                "(Forbidden) Caller is not authorized to perform action on "
                "resource."
            ),
        )
        assert "Key Vault Secrets User" in message
        assert "not found" not in message.lower()

    def test_an_unreachable_vault_is_not_read_as_a_login_prompt(
        self, tmp_path: Path
    ) -> None:
        """The uncoded path echoes names too — the assumption that broke this.

        A DNS failure carries no Azure error code *and* quotes the host, so
        "an echoed name always arrives with a code" was false exactly here. A
        logged-in user was told to log in, and the real failure vanished.

        The vault that proved it was literally named `az login`, which issue #60
        now refuses before any lookup. The anchoring this pins is not about that
        one name: az writes the phrase mid-sentence in the reply to a perfectly
        legal vault too, and only the message-start anchor keeps it inert.
        """
        vault = "unreachable-kv"
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                f"HTTPSConnection(host='{vault}.vault.azure.net', port=443): "
                f"Failed to resolve '{vault}.vault.azure.net' — "
                f"please run 'az login' if this persists"
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"akv://{vault}/a-secret", context(tmp_path))
        message = caught.value.message
        assert "could not be reached" in message
        assert "is not logged in" not in message, "the phrase claimed the branch"

    def test_the_real_login_message_is_still_recognised(
        self, tmp_path: Path
    ) -> None:
        """Anchoring must not cost the diagnosis it exists for (verified text)."""
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error("Please run 'az login' to setup account."),
        )
        with pytest.raises(SecretResolutionError, match="Run: az login"):
            resolve("K", REF, context(tmp_path))

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
        """Where the earlier code anchoring still leaked: a code spelled in prose.

        `(Forbidden)` is not a legal Key Vault name, which was the point — az
        rejected it with `BadParameter` and echoed it into the message, where a
        scan for `(forbidden)` found it and reported a denial. Codes are read
        only from the fields az writes codes in, so the echo is inert.

        Issue #60 stops that name being a name at all; the parenthesised token
        still has to stay inert wherever else az's prose puts one, which is what
        a second parenthesis on the same line is here to prove.
        """
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(BadParameter) The request URI contains an invalid name "
                "(Forbidden) is not among the accepted forms"
            )
            + "Code: BadParameter\n",
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", REF, context(tmp_path))
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
            resolve("K", f"{REF}/{VERSION}", context(tmp_path))
        assert f"--version {VERSION}" in caught.value.message

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

    def test_a_json_escape_for_a_lone_surrogate_is_refused_not_returned(
        self, tmp_path: Path
    ) -> None:
        """`json.loads` is the one way a *resolved* value can carry a surrogate.

        az's output is decoded UTF-8 strict, so no surrogate survives that — but
        a JSON escape is not a decode, and nothing downstream can represent what
        it produces: `encode_env` encodes with `surrogateescape`, which would
        hand the child a raw byte instead of the value's UTF-8 — a different
        secret than the vault holds, with nothing raised. That handler is right
        for an inherited value (`env://` resolves to one), so the refusal
        belongs where a value's provenance is still known.

        Refused for every provider at once in `resolver._representable`, not
        here — a rule keyed on this provider, or on the spelling `json.loads`,
        is one the next provider walks past.
        `tests/architecture/test_child_env_encoding.py` exercises every
        installed provider with the same value.
        """
        body = "recognisable-secret-body"
        fake_az(tmp_path / "bin", stdout=f'"\\ud800{body}"')
        with pytest.raises(SecretResolutionError, match="unpaired surrogate") as caught:
            resolve("K", REF, context(tmp_path))
        assert body not in caught.value.message
        assert "d800" not in caught.value.message.lower(), "not even as an escape"

    def test_a_paired_surrogate_escape_is_an_ordinary_character(
        self, tmp_path: Path
    ) -> None:
        """The control: `\\uD83D\\uDE00` is a valid pair, and must still resolve.

        Without this, refusing every `\\u`-escaped astral character would pass
        the test above just as well.
        """
        fake_az(tmp_path / "bin", stdout='"grin-\\ud83d\\ude00"')
        assert resolve("K", REF, context(tmp_path)) == "grin-\U0001f600"

    def test_an_az_that_never_answers_is_reported_as_a_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one branch no canned answer can reach — the child must really hang.

        The timeout itself is shortened; everything else, including the kill, is
        the shipped path.
        """
        monkeypatch.setattr(azurekeyvault, "TIMEOUT", 0.3)
        slow_az(tmp_path / "bin", seconds=10)
        with pytest.raises(SecretResolutionError, match="timed out"):
            resolve("K", REF, context(tmp_path))

    # `akv://v/s/latest` and `akv://v/bad_name/abc123` used to be diagnosed from
    # az's reply here. Both are refused without a call now, which is issue #60's
    # point; `TestSegmentsAreValidatedBeforeAzIsSpawned` holds those cases, and
    # the `/latest` guidance with them. What remains below is the branch that is
    # still reachable: az answering BadParameter about a well-formed reference.

    def test_an_operation_refusal_about_another_version_is_not_borrowed(
        self, tmp_path: Path
    ) -> None:
        """The anchor names *this* version, so other text cannot claim the branch.

        az quotes a refused operation in its message, and nothing says the quoted
        name is the version this reference pinned — an earlier form of this test
        spelled a different one on both sides, so the anchor could not have
        matched either way and it passed without exercising anything.
        """
        fake_az(
            tmp_path / "bin",
            code=1,
            stderr=azure_error(
                "(BadParameter) Method GET does not allow operation 'somethingelse'"
            ),
        )
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"{REF}/{VERSION}", context(tmp_path))
        message = caught.value.message
        assert "is not a version id" not in message, "a different name claimed it"
        assert "list-versions" not in message
        assert "does not allow operation" in message, "az's real reason must survive"

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
    `[sandbox.secrets]` entry is one too — and interpolating its segments raw put
    a command substitution into text a human is told to paste into a shell.

    Since issue #60 no segment carrying one can get past `_parse`, so these
    call the builder directly rather than pretending a reference could still
    deliver the payload. The quoting is kept, and kept under test, because the
    guarantee belongs to the function that writes the line: the next caller need
    not know how far away the validation is, or whether it still holds.

    The property is what a *shell* would make of the command, so the assertions
    parse it with `shlex.split` rather than looking for quote characters.
    """

    # The spaces are load-bearing for the *test*, not the attack: `shlex.split`
    # tokenizes, it does not evaluate, so a payload with no space comes back as
    # one token whether or not it was ever quoted, and the assertion below could
    # not fail. With spaces, unquoted guidance tokenizes into several arguments
    # and the test goes red — which is the only reason it is worth running.
    HOSTILE = "$(id) ; whoami"

    def test_a_hostile_segment_stays_one_literal_argument_in_the_retry(self) -> None:
        command = azurekeyvault._retry("a-vault", self.HOSTILE, None)
        assert shlex.split(command) == [
            "az", "keyvault", "secret", "show",
            "--vault-name", "a-vault", "--name", self.HOSTILE,
            "--output", "none",
        ], "a shell would run the segment instead of passing it"

    def test_a_hostile_segment_stays_one_literal_argument_in_list_versions(
        self,
    ) -> None:
        command = azurekeyvault._az_command(
            "list-versions", "--vault-name", "a-vault", "--name", self.HOSTILE
        )
        assert shlex.split(command) == [
            "az", "keyvault", "secret", "list-versions",
            "--vault-name", "a-vault", "--name", self.HOSTILE,
        ]

    def test_a_segment_carrying_a_single_quote_still_survives_whole(self) -> None:
        """The case that separates real quoting from a wrapper in quotes.

        `shlex.join` encloses in single quotes, so an embedded `'` has to be
        broken out and re-escaped. A hand-rolled `f"'{segment}'"` renders this
        payload as three shell words and passes every other test in this class.
        """
        payload = "it's $(id); rm -rf ~"
        command = azurekeyvault._retry("a-vault", payload, None)
        assert shlex.split(command) == [
            "az", "keyvault", "secret", "show",
            "--vault-name", "a-vault", "--name", payload,
            "--output", "none",
        ]

    def test_an_ordinary_name_is_not_dressed_up_in_quotes(
        self, tmp_path: Path
    ) -> None:
        """Quoting must not make the message a real failure prints any uglier.

        Through `resolve`, because this one is about what an operator actually
        sees: every name a reference can still carry is an ordinary one.
        """
        fake_az(tmp_path / "bin", code=1, stderr="")
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", f"{REF}/{VERSION}", context(tmp_path))
        assert (
            f"az keyvault secret show --vault-name a-vault --name a-secret "
            f"--version {VERSION} --output none"
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


# --- Azure's own name rules, applied before az is spawned ---


class TestSegmentsAreValidatedBeforeAzIsSpawned:
    """The class of defect this closes: a segment az echoes back into its error.

    Rounds 6-11 of PR #49 were each one unvalidated segment reappearing inside
    `az`'s message — a name spelling an error code, a NUL, a line break forging a
    `Code:` line, a name reading `disabled secret`, a name claiming the login
    branch. Each was patched where it surfaced. Azure will not accept any of
    those names in the first place, so refusing them here ends the class rather
    than the instance, and ends the doomed round-trip with it.

    Every test asserts az was never spawned, because "refused at the source" is
    the property, not merely "refused".
    """

    VALID_VERSION = "3a7f1c9e2b4d5068a1c3e5f7092b4d6e"

    def refuse(self, ref: str, tmp_path: Path) -> str:
        """The message for a refused reference, proving az never ran."""
        log = fake_az(tmp_path / "bin", stdout=json.dumps("never-read"))
        with pytest.raises(SecretResolutionError) as caught:
            resolve("K", ref, context(tmp_path))
        assert not log.exists(), "az was spawned for a reference Azure would reject"
        return caught.value.message

    # --- vaults ---

    @pytest.mark.parametrize(
        ("vault", "why"),
        [
            ("kv", "two characters is below Azure's minimum of three"),
            ("k" * 25, "twenty-five is above Azure's maximum of twenty-four"),
            ("my_vault", "an underscore is not a Key Vault name character"),
            ("az login", "the round-6 vault: a space, and a DNS echo with no code"),
            ("kv.1", "a dot is not one either"),
            ("café-kv", "nor is an accent, however readable"),
        ],
    )
    def test_a_vault_azure_would_reject_never_reaches_it(
        self, vault: str, why: str, tmp_path: Path
    ) -> None:
        message = self.refuse(f"akv://{vault}/a-secret", tmp_path)
        assert "is not a Key Vault name" in message, why
        assert vault in message, "the offending segment is not named"

    @pytest.mark.parametrize("vault", ["kv1", "k" * 24, "kv-devops-ai-accept"])
    def test_a_vault_azure_accepts_is_left_alone(
        self, vault: str, tmp_path: Path
    ) -> None:
        """The bounds are inclusive, and the real acceptance vault is one of them."""
        fake_az(tmp_path / "bin", stdout=json.dumps("v"))
        assert resolve("K", f"akv://{vault}/a-secret", context(tmp_path)) == "v"

    # --- secrets ---

    @pytest.mark.parametrize(
        ("secret", "why"),
        [
            ("my_secret", "the underscore the issue names: a clear message at last"),
            ("café-name", "an accent Azure will not store"),
            ("(Forbidden)", "the round-7 name that was read back as an error code"),
            ("disabled secret", "the round-10 name that claimed a vault state"),
            ("$(id) ; whoami", "a payload that had to be quoted out of guidance"),
            ("a.b", "a dot: legal in a hostname, not in a secret name"),
        ],
    )
    def test_a_secret_azure_would_reject_never_reaches_it(
        self, secret: str, why: str, tmp_path: Path
    ) -> None:
        message = self.refuse(f"akv://a-vault/{secret}", tmp_path)
        assert "is not a Key Vault secret name" in message, why
        assert secret in message, "the offending segment is not named"

    @pytest.mark.parametrize("secret", ["s", "a-secret", "A1-b2", "9"])
    def test_a_secret_azure_accepts_is_left_alone(
        self, secret: str, tmp_path: Path
    ) -> None:
        """Deliberately unbounded in length: Key Vault caps a secret name and
        this does not, so the rule refuses only what Azure certainly would."""
        fake_az(tmp_path / "bin", stdout=json.dumps("v"))
        assert resolve("K", f"akv://a-vault/{secret}", context(tmp_path)) == "v"

    # --- versions ---

    @pytest.mark.parametrize(
        ("version", "why"),
        [
            ("latest", "what an operator writes when they mean the current version"),
            ("abc123", "hexadecimal, but six characters of it"),
            ("0" * 31, "one short"),
            ("0" * 33, "one over"),
            ("g" * 32, "thirty-two characters, none of them hexadecimal"),
            ("does not allow operation 'zz99'", "the round-11 impostor"),
        ],
    )
    def test_a_version_that_is_not_an_id_never_reaches_azure(
        self, version: str, why: str, tmp_path: Path
    ) -> None:
        message = self.refuse(f"{REF}/{version}", tmp_path)
        assert "is not a version id" in message, why
        assert version in message, "the offending segment is not named"

    def test_the_refused_version_still_says_where_to_find_a_real_one(
        self, tmp_path: Path
    ) -> None:
        """The guidance survives the round-trip it replaces.

        On main, `akv://v/s/latest` spent a network call to learn that Key Vault
        reads a non-id segment as an operation name; the message built from that
        answer is the useful one. Refusing at the source must not cost it.
        """
        message = self.refuse(f"{REF}/latest", tmp_path)
        assert "Omit it to read the current version" in message
        assert (
            "az keyvault secret list-versions --vault-name a-vault --name a-secret"
            in message
        )

    @pytest.mark.parametrize(
        "version", [VALID_VERSION, VALID_VERSION.upper(), "0" * 32]
    )
    def test_a_real_version_id_is_left_alone(
        self, version: str, tmp_path: Path
    ) -> None:
        """Azure writes ids in lowercase; upper case is accepted rather than
        risk refusing an id a caller pasted from somewhere that changed it."""
        log = fake_az(tmp_path / "bin", stdout=json.dumps("v"))
        assert resolve("K", f"{REF}/{version}", context(tmp_path)) == "v"
        assert recorded(log)[-2:] == ["--version", version]

    # --- the shape of a refusal ---

    def test_the_secret_is_blamed_before_the_version(self, tmp_path: Path) -> None:
        """Two bad segments name the first one, not whichever is checked last.

        On main this reference reached az, whose BadParameter answer had to be
        kept from being blamed on the version. Order does that work now.
        """
        message = self.refuse("akv://a-vault/bad_name/abc123", tmp_path)
        assert "bad_name" in message and "secret name" in message
        assert "version id" not in message

    def test_an_unprintable_character_is_escaped_not_echoed(
        self, tmp_path: Path
    ) -> None:
        """A refused segment is attacker-shaped by definition.

        It is named in a message an operator reads in a terminal, so an ANSI
        escape in it would be executed by the terminal rather than shown. Only
        the unprintable characters are escaped: an accent stays an accent, or
        the message hides the very thing it is about.
        """
        message = self.refuse("akv://a-vault/x\x1b[2Ky", tmp_path)
        assert "\\x1b" in message
        assert "\x1b" not in message

    def test_check_reports_a_refused_reference_rather_than_raising(
        self, tmp_path: Path
    ) -> None:
        """`check` classifies; it never crashes on input it was asked to judge."""
        fake_az(tmp_path / "bin", stdout=json.dumps("never-read"))
        assert check("K", "akv://a-vault/my_secret", context(tmp_path)).status == ERROR

    @pytest.mark.parametrize(
        ("pattern", "segment"),
        [
            (azurekeyvault._VAULT_NAME, "a-vault"),
            (azurekeyvault._SECRET_NAME, "a-secret"),
            (azurekeyvault._VERSION_ID, "0" * 32),
        ],
    )
    def test_no_rule_accepts_a_segment_ending_in_a_newline(
        self, pattern: "re.Pattern[str]", segment: str
    ) -> None:
        """`$` matches before a final newline; `\\Z` does not.

        Written against the patterns rather than through `resolve`, because the
        line-break guard refuses such a reference first and would make the test
        pass whichever anchor these carried — green, and blind. A newline in a
        segment is what rounds 6-11 were about, so the rule that screens segments
        has to refuse one on its own, not by standing behind another check.
        """
        assert pattern.match(segment) is not None, "the sound segment is refused"
        assert pattern.match(segment + "\n") is None

    def test_a_refusal_never_quotes_a_value(self, tmp_path: Path) -> None:
        """The reference is not the secret, but az's stdout is — and az did not
        run, so there is nothing of the vault's in the message by construction."""
        message = self.refuse("akv://a-vault/my_secret", tmp_path)
        assert "never-read" not in message
