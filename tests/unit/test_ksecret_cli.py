"""Tests for the ksecret CLI's own wiring.

The end-to-end behavior of read/run/check lives in the acceptance suite, which
runs the real console script. What is worth pinning here is the part the CLI
itself decides: which references it collects, and where it resolves them from.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devops_ai.cli.ksecret import _base_environment, app

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

    def test_all_resolving_exits_zero(self, project: Path) -> None:
        infra = project / ".devops-ai" / "infra.toml"
        infra.write_text(
            infra.read_text().replace('MISSING = "$NOT_SET_ANYWHERE"\n', "")
        )
        result = runner.invoke(app, ["check", "--infra"])
        assert result.exit_code == 0, result.output

    def test_outside_a_project_it_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--infra"])
        assert result.exit_code == 1


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

    def test_an_env_file_key_is_not_redacted(self, project: Path) -> None:
        """Keys come from the file, not from the value — echoing them is safe."""
        (project / "refs.env").write_text("CONN=postgres://user:hunter2@host/db\n")
        result = runner.invoke(app, ["check", "--env-file", "refs.env"])
        assert "CONN: literal" in result.output
        assert "hunter2" not in result.output


class TestTheEnvironmentReferencesResolveIn:
    """Literal lines are declarations, so they beat whatever the shell exported."""

    def test_a_literal_line_overrides_the_parent_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OP_ACCOUNT", "stale-from-the-shell")
        environ = _base_environment({"OP_ACCOUNT": "declared.1password.com"})
        assert environ["OP_ACCOUNT"] == "declared.1password.com"

    def test_the_parent_environment_still_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNRELATED", "from-the-shell")
        assert _base_environment({"K": "literal"})["UNRELATED"] == "from-the-shell"

    def test_references_are_not_placed_before_they_resolve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("A", raising=False)
        assert "A" not in _base_environment({"A": "dotenv://.env#A"})
