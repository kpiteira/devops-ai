"""The Azure Key Vault provider, exercised through the resolver's public surface.

No patching: `az` is replaced at the seam that is actually slow and non-deterministic
— the subprocess — by a real executable on the PATH the provider is given. Everything
between `resolve()` and that boundary is the shipped code.
"""

from __future__ import annotations

import json
import os
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

    def test_check_reports_the_failure_as_error(self, tmp_path: Path) -> None:
        fake_az(
            tmp_path / "bin", code=3, stderr=azure_error("(SecretNotFound) gone")
        )
        assert check("K", REF, context(tmp_path)).status == ERROR


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
