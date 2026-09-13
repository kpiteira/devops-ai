"""`ksecret run` hands its child a *bytes* environment, and exec still works.

Encoding the environment ourselves (#58) moved `subprocess` onto a different
branch: given a bytes mapping it resolves a bare command name through
`os.get_exec_path`, which reads `b"PATH"` rather than `"PATH"`. Every other
test of `run` passes an absolute program, so none of them would notice that
branch breaking — and `ksecret run -- pytest` is the ordinary way to use it.

These are locale-independent on purpose: the bytes environment is now the only
code path, so it has to hold on a developer's UTF-8 machine too. The C-locale
half of the promise lives in `test_secret_locale.py`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALUE = "plain-ascii-value"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / ".env").write_text(f"K={VALUE}\n", encoding="utf-8")
    (tmp_path / "refs.env").write_text("A=dotenv://.env#K\n")
    return tmp_path


def _ksecret(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--project", str(ROOT), "ksecret", *args],
        cwd=cwd, capture_output=True, text=True, timeout=300,
    )


def test_a_bare_command_name_is_still_found_on_path(project: Path) -> None:
    """`env` by name, not by path — the lookup a bytes environment changes."""
    result = _ksecret(
        "run", "--env-file", "refs.env", "--", "env", cwd=project
    )
    assert result.returncode == 0, result.stderr
    assert f"A={VALUE}" in result.stdout.splitlines()


def test_a_bare_command_that_does_not_exist_still_reports_itself(
    project: Path,
) -> None:
    """The OSError arm has to survive the new branch, or this is a traceback."""
    result = _ksecret(
        "run", "--env-file", "refs.env", "--",
        "no-such-program-anywhere", cwd=project,
    )
    assert result.returncode == 127
    assert "cannot execute no-such-program-anywhere" in result.stderr
    assert VALUE not in result.stderr, "the resolved value must not leak"
