"""Tests for the ksecret CLI's own wiring.

The end-to-end behavior of read/run/check lives in the acceptance suite, which
runs the real console script. What is worth pinning here is the part the CLI
itself decides: which references it collects, and where it resolves them from.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devops_ai.cli import ksecret
from devops_ai.cli.ksecret import app

runner = CliRunner()


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".devops-ai").mkdir()
    (tmp_path / ".env").write_text("DB_PASSWORD=hunter2\n")
    (tmp_path / ".devops-ai" / "infra.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        'prefix = "demo"\n'
        "\n"
        "[sandbox]\n"
        'compose_file = "docker-compose.yml"\n'
        "\n"
        "[sandbox.secrets]\n"
        'DB_PASSWORD = "dotenv://.env#DB_PASSWORD"\n'
        'OP_ACCOUNT = "my-team.1password.com"\n'
        'MISSING = "$NOT_SET_ANYWHERE"\n'
    )
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NOT_SET_ANYWHERE", raising=False)
    return tmp_path


class TestCheckInfra:
    def test_classifies_the_project_s_sandbox_secrets(self, project: Path) -> None:
        result = runner.invoke(app, ["check", "--infra"])
        assert result.exit_code == 1
        lines = dict(
            line.split(":", 1) for line in result.output.splitlines() if ":" in line
        )
        assert lines["DB_PASSWORD"].strip() == "ok"
        assert lines["OP_ACCOUNT"].strip() == "literal"
        assert lines["MISSING"].strip().startswith("error")
        assert "hunter2" not in result.output

    def test_a_project_with_no_declared_secrets_is_a_usage_error_not_a_green(
        self, project: Path
    ) -> None:
        """--infra reached the same "checked nothing" green the guard rejects."""
        infra = project / ".devops-ai" / "infra.toml"
        infra.write_text(infra.read_text().split("[sandbox.secrets]")[0])

        result = runner.invoke(app, ["check", "--infra"])
        assert result.exit_code == 2
        assert "nothing to check" in result.output
        assert "no sandbox secrets" in result.output

    def test_all_resolving_exits_zero(self, project: Path) -> None:
        infra = project / ".devops-ai" / "infra.toml"
        infra.write_text(
            infra.read_text().replace('MISSING = "$NOT_SET_ANYWHERE"\n', "")
        )
        result = runner.invoke(app, ["check", "--infra"])
        assert result.exit_code == 0, result.output

    def test_outside_a_git_repository_it_refuses_like_kinfra_does(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """kinfra errors rather than guessing a root; --infra must not differ."""
        (tmp_path / ".devops-ai").mkdir()
        (tmp_path / ".env").write_text("FROM_FILE=secret-value\n")
        (tmp_path / ".devops-ai" / "infra.toml").write_text(
            '[project]\nname = "demo"\nprefix = "demo"\n\n'
            '[sandbox]\ncompose_file = "docker-compose.yml"\n\n'
            '[sandbox.secrets]\nX = "dotenv://.env#FROM_FILE"\n'
        )
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--infra"])

        assert result.exit_code == 1
        assert "main repository root" in result.output
        assert "X: ok" not in result.output, "it cannot know that from here"

    def test_outside_a_project_it_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--infra"])
        assert result.exit_code == 1


class TestInfraReportsWhatKinfraWillDo:
    """--infra's whole promise is agreement with kinfra. A confident wrong
    answer about that is worse than the green no-op it replaced."""

    @staticmethod
    def _declare(project: Path, body: str) -> None:
        infra = project / ".devops-ai" / "infra.toml"
        head = infra.read_text().split("[sandbox.secrets]")[0]
        infra.write_text(f"{head}[sandbox.secrets]\n{body}")

    def test_a_reference_to_a_declared_literal_resolves(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("A", raising=False)
        self._declare(project, 'A = "declared-value"\nB = "$A"\n')

        result = runner.invoke(app, ["check", "--infra"])

        assert result.exit_code == 0, result.output
        assert "B: ok" in result.output
        assert "A: literal" in result.output
        assert "declared-value" not in result.output

    def test_it_agrees_with_what_resolve_all_secrets_returns(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The two paths are checked against each other, not against a guess."""
        from devops_ai.provision import resolve_all_secrets

        monkeypatch.delenv("A", raising=False)
        secrets = {"A": "declared-value", "B": "$A"}
        self._declare(project, 'A = "declared-value"\nB = "$A"\n')

        resolved, errors = resolve_all_secrets(secrets, project)
        result = runner.invoke(app, ["check", "--infra"])

        assert errors == [], "kinfra resolves this"
        assert set(resolved) == set(secrets)
        assert "error" not in result.output, "so --infra must not call it an error"
        assert result.exit_code == 0


class TestCheckCollectsFromEveryInput:
    def test_env_file_and_bare_references_are_both_reported(
        self, project: Path
    ) -> None:
        (project / "refs.env").write_text(
            "FROM_FILE=dotenv://.env#DB_PASSWORD\nLIT=plain\n"
        )
        result = runner.invoke(
            app, ["check", "--env-file", "refs.env", "dotenv://.env#DB_PASSWORD"]
        )
        assert result.exit_code == 0, result.output
        assert "FROM_FILE: ok" in result.output
        assert "LIT: literal" in result.output
        assert "dotenv://.env#DB_PASSWORD: ok" in result.output
        assert "hunter2" not in result.output

    def test_checking_nothing_is_a_usage_error_not_a_green(
        self, project: Path
    ) -> None:
        """An empty success reads as "all secrets fine" to whoever runs it."""
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 2
        assert "nothing to check" in result.output

    def test_an_env_file_that_collects_nothing_is_still_a_usage_error(
        self, project: Path
    ) -> None:
        """Passing --env-file is not the same as having something to check."""
        (project / "empty.env").write_text("# only a comment\n\n")
        result = runner.invoke(app, ["check", "--env-file", "empty.env"])
        assert result.exit_code == 2
        assert "nothing to check" in result.output

    def test_a_nonempty_env_file_is_checked_normally(self, project: Path) -> None:
        (project / "one.env").write_text("# a comment\nA=dotenv://.env#DB_PASSWORD\n")
        result = runner.invoke(app, ["check", "--env-file", "one.env"])
        assert result.exit_code == 0, result.output
        assert "A: ok" in result.output

    def test_an_undecodable_env_file_is_an_error_not_a_traceback(
        self, project: Path
    ) -> None:
        (project / "binary.env").write_bytes(b"A=\xff\xfe\n")
        result = runner.invoke(app, ["check", "--env-file", "binary.env"])
        assert result.exit_code == 1
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "binary.env" in result.output

    def test_a_missing_env_file_is_an_error_not_a_traceback(
        self, project: Path
    ) -> None:
        result = runner.invoke(app, ["check", "--env-file", "nope.env"])
        assert result.exit_code == 1
        assert result.exception is None or isinstance(result.exception, SystemExit)


class TestRunRefuses:
    def test_no_command_is_a_usage_error(self, project: Path) -> None:
        result = runner.invoke(app, ["run"])
        assert result.exit_code == 2

    def test_an_unexecutable_command_is_a_message_not_a_crash(
        self, project: Path
    ) -> None:
        (project / "refs.env").write_text("A=dotenv://.env#DB_PASSWORD\n")
        result = runner.invoke(
            app, ["run", "--env-file", "refs.env", "--", "definitely-not-a-command"]
        )
        assert result.exit_code == 127
        assert "cannot execute definitely-not-a-command" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "hunter2" not in result.output

    def test_a_non_executable_file_is_the_same_clean_failure(
        self, project: Path
    ) -> None:
        target = project / "not-a-program"
        target.write_text("data\n")
        result = runner.invoke(app, ["run", "--", str(target)])
        assert result.exit_code == 127
        assert "cannot execute" in result.output

    def test_a_value_with_no_utf8_encoding_is_exit_1_not_a_traceback(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The `EnvironmentEncodingError` catch, exercised through the CLI.

        `tests/unit/test_secrets_environ.py` pins that `encode_env` *raises*;
        nothing pinned what `run` does with it. Deleting the catch left all 558
        unit and architecture tests green while the command printed a traceback
        — measured, which is why this exists.

        The value is injected at `resolve_all` rather than written into a file
        because no input channel can carry a lone surrogate: a file's bytes and
        `sys.argv` alike are decoded with `surrogateescape`, which lands in
        U+DC80..U+DCFF, the range that encodes back cleanly. Only a text format
        a provider parses can manufacture U+D800, and `resolver` now refuses
        that for every provider but `env://`. So the real `encode_env` and the
        real catch both run here; only the source that cannot be reached is
        stood in for.
        """
        monkeypatch.setattr(
            ksecret, "resolve_all", lambda refs, ctx: ({"TOKEN": "s3cr3t-\ud800"}, [])
        )
        (project / "refs.env").write_text("TOKEN=dotenv://.env#DB_PASSWORD\n")
        result = runner.invoke(app, ["run", "--env-file", "refs.env", "--", "true"])

        assert result.exit_code == 1, result.output
        assert "ksecret run:" in result.output
        assert "unpaired surrogate" in result.output
        assert "TOKEN" in result.output, "the refusal has to name the variable"
        # Never the value, never the escape, never a chained traceback under it.
        assert "s3cr3t" not in result.output
        assert "d800" not in result.output.lower()
        assert "Traceback" not in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)


class TestALiteralIsNeverEchoedWithoutPrint:
    """A literal is its own value, so a confirmation that names it is a leak."""

    LITERAL = "postgres://user:hunter2@host/db"

    def test_read_confirms_a_literal_without_repeating_it(
        self, project: Path
    ) -> None:
        result = runner.invoke(app, ["read", self.LITERAL])
        assert result.exit_code == 0, result.output
        assert "hunter2" not in result.output
        assert result.output.strip() == "ok (literal)"

    def test_check_reports_a_bare_literal_without_repeating_it(
        self, project: Path
    ) -> None:
        result = runner.invoke(app, ["check", self.LITERAL])
        assert result.exit_code == 0, result.output
        assert "hunter2" not in result.output
        assert "literal" in result.output

    def test_print_still_emits_it_because_that_is_the_explicit_ask(
        self, project: Path
    ) -> None:
        result = runner.invoke(app, ["read", "--print", self.LITERAL])
        assert result.exit_code == 0
        assert result.output.strip() == self.LITERAL

    def test_a_real_reference_still_names_itself(self, project: Path) -> None:
        """Redaction applies to values, not to references — those are not secret."""
        ref = "dotenv://.env#DB_PASSWORD"
        result = runner.invoke(app, ["read", ref])
        assert result.output.strip() == f"ok {ref}"
        assert "hunter2" not in result.output

    def test_a_refused_stdin_names_the_reference_it_was_meant_for(
        self, project: Path
    ) -> None:
        """`errors name the reference` covers the input failure too.

        A provisioning run pipes many secrets through this command; a refusal
        that names none of them says only that *something* was not text.
        """
        ref = "dotenv://out.env#K"
        result = runner.invoke(app, ["write", ref], input=b"\xff\xfe not text")

        assert result.exit_code == 1
        assert ref in result.output

    def test_a_refused_stdin_still_does_not_echo_a_literal(
        self, project: Path
    ) -> None:
        """The mirror, and the reason the reference goes through `_label`.

        Naming the "reference" here would print the value itself, which is the
        one thing every other path in this command is careful not to do.
        """
        result = runner.invoke(
            app, ["write", self.LITERAL], input=b"\xff\xfe not text"
        )

        assert result.exit_code == 1
        assert "hunter2" not in result.output
        assert "(literal)" in result.output

    def test_an_env_file_key_is_not_redacted(self, project: Path) -> None:
        """Keys come from the file, not from the value — echoing them is safe."""
        (project / "refs.env").write_text("CONN=postgres://user:hunter2@host/db\n")
        result = runner.invoke(app, ["check", "--env-file", "refs.env"])
        assert "CONN: literal" in result.output
        assert "hunter2" not in result.output


ACCENTED = "café-über"


def filesystem_encoding(monkeypatch: pytest.MonkeyPatch, codec: str) -> None:
    """`os.fsencode` as it behaves under a given locale, installed by hand.

    macOS hardcodes its filesystem encoding to UTF-8 whatever `LC_ALL` says, so
    a locale fixture is inert there and the codec has to be installed instead.
    Bytes pass through untouched, as the real `os.fsencode` does — `subprocess`
    puts a bytes environment back through it — and `surrogateescape` is the real
    handler, not `strict`: getting that wrong would make the controls below red
    for the wrong reason and look like a finding.

    Two codecs, because they answer different questions. `ascii` is `LC_ALL=C`,
    where a value we authored cannot be spelled at all. `iso8859-15` is the
    harder case: every byte decodes, so nothing fails — the two encoders simply
    disagree about which bytes a character is, and only there can a test tell
    `utf-8` from the locale apart on a value that holds no surrogate.
    """

    def locale_codec(value: object) -> bytes:
        if isinstance(value, bytes):
            return value
        return str(value).encode(codec, "surrogateescape")

    monkeypatch.setattr(os, "fsencode", locale_codec)


def only_this_environment(monkeypatch: pytest.MonkeyPatch, **names: str) -> None:
    """Start from an empty environment, so the developer's own cannot decide."""
    for key in list(os.environ):
        monkeypatch.delenv(key, raising=False)
    for key, value in names.items():
        monkeypatch.setenv(key, value)


def fake_op(directory: Path, log: Path) -> None:
    """An `op` that records the bytes of one variable it was spawned with."""
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "op"
    program.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, sys\n"
        f"pathlib.Path({str(log)!r}).write_bytes(os.environb.get(b'GREETING', b''))\n"
        "sys.stdout.write('resolved-secret')\n",
        encoding="utf-8",
    )
    program.chmod(0o755)


def test_a_declared_literal_reaches_a_provider_child_as_its_own_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`op` is a child too, and a literal declared beside a reference is ours.

    An env file's literal lines are laid over the process environment *before*
    anything resolves, precisely so a declared `OP_ACCOUNT` reaches the `op`
    that the next line spawns — `literals()` says so, and kinfra's `_context`
    repeats it. So that spawn carries the same promise as the final one: the
    value was read from a file devops-ai decodes as strict UTF-8, which means it
    can hold characters the operator's locale cannot spell. Handing it to the
    locale's codec instead fails the whole command under `LC_ALL=C`.
    """
    bin_dir = tmp_path / "bin"
    log = tmp_path / "seen-by-op"
    fake_op(bin_dir, log)

    env_file = tmp_path / "f.env"
    env_file.write_text(
        f"GREETING={ACCENTED}\nTOKEN=op://v/i/f\n", encoding="utf-8"
    )

    only_this_environment(monkeypatch, PATH=str(bin_dir))
    filesystem_encoding(monkeypatch, "ascii")

    result = runner.invoke(
        app, ["run", "--env-file", str(env_file), "--", sys.executable, "-c", ""]
    )

    assert result.exit_code == 0, result.output
    assert log.read_bytes() == ACCENTED.encode("utf-8"), (
        "the provider child got the locale's spelling of a value we authored"
    )


def test_an_inherited_value_still_is_not_respelled_for_a_provider_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control, in the other direction — and the reason for the PATH fix.

    Declaring the literals must not re-open what `utf8_keys` closed: a variable
    the env file never named is still handed on exactly as this process holds
    it, so "fix the literals" cannot be satisfied by encoding the whole
    environment again — the regression that started this.

    `iso8859-15` and a real character, for the same reason as the test below:
    the first draft used a surrogate under `ascii`, and a surrogate round-trips
    to the identical byte through *either* encoder. It asserted the right bytes
    and could not have gone red for the mechanism it names.
    """
    bin_dir = tmp_path / "bin"
    log = tmp_path / "seen-by-op"
    fake_op(bin_dir, log)

    env_file = tmp_path / "f.env"
    env_file.write_text("TOKEN=op://v/i/f\n", encoding="utf-8")

    only_this_environment(monkeypatch, PATH=str(bin_dir))
    # Inherited, and named nowhere in the env file.
    monkeypatch.setenv("GREETING", "café")
    filesystem_encoding(monkeypatch, "iso8859-15")

    result = runner.invoke(
        app, ["run", "--env-file", str(env_file), "--", sys.executable, "-c", ""]
    )

    assert result.exit_code == 0, result.output
    assert log.read_bytes() == "café".encode("iso8859-15"), (
        "an inherited value must go back out as the bytes it came in as"
    )


def test_a_reference_named_after_an_inherited_variable_is_not_claimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Declaring the *literals* is not the same as declaring the entries.

    An entry whose value is a reference has not been laid over the environment
    yet — until it resolves, that name still holds whatever this process
    inherited. Claiming every entry name instead would hand the provider child a
    re-spelled value, which is the regression `utf8_keys` was added to undo, so
    this is the one spelling of `declared` that looks equivalent and is not.

    It takes `iso8859-15` to see. Under `ascii` the two encoders agree on every
    value that survives both, so the first draft of this test passed with
    `declared` spelled either way — a check that was green in the broken case
    and the healthy one alike, which is the defect this suite exists to catch.
    """
    bin_dir = tmp_path / "bin"
    log = tmp_path / "seen-by-op"
    fake_op(bin_dir, log)

    env_file = tmp_path / "f.env"
    # GREETING is an entry name *and* a reference, so it is not laid over the
    # environment until it resolves: what `op` sees is still the inherited one.
    env_file.write_text("GREETING=op://v/i/f\n", encoding="utf-8")

    only_this_environment(monkeypatch, PATH=str(bin_dir))
    # A real character, not a surrogate: a surrogate round-trips to the same
    # byte through either encoder, so it could not tell the two apart.
    monkeypatch.setenv("GREETING", "café")
    filesystem_encoding(monkeypatch, "iso8859-15")

    result = runner.invoke(
        app, ["run", "--env-file", str(env_file), "--", sys.executable, "-c", ""]
    )

    assert result.exit_code == 0, result.output
    assert log.read_bytes() == "café".encode("iso8859-15"), (
        "an entry name that is a reference must not claim the inherited value"
    )
