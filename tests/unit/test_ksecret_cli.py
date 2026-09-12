"""Tests for the ksecret CLI's own wiring.

The end-to-end behavior of read/run/check lives in the acceptance suite, which
runs the real console script. What is worth pinning here is the part the CLI
itself decides: which references it collects, and where it resolves them from.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

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
