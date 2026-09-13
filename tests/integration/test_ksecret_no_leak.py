"""An unhandled error must not print a resolved secret.

Typer renders frame locals in its rich traceback by default, and `ksecret run`
holds the child's whole environment — every resolved value — in a frame local.
Before `pretty_exceptions_show_locals=False`, the value below appeared twice on
stderr. Only the real console script exercises Typer's exception hook, so this
runs the installed command rather than CliRunner.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALUE = "tOpSeCrEtVaLuE12345"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    # A NUL byte in the value survives resolution and makes the exec raise
    # ValueError from deep inside subprocess — an error nothing here handles.
    (tmp_path / ".env").write_bytes(f"SUPER={VALUE}\0tail\n".encode())
    (tmp_path / "refs.env").write_text("A=dotenv://.env#SUPER\n")
    return tmp_path


def test_a_crash_inside_run_prints_no_value(project: Path) -> None:
    result = _ksecret(
        "run", "--env-file", "refs.env", "--", "/bin/echo", "hi", cwd=project
    )
    assert result.returncode != 0, "the NUL byte must still fail the run"
    assert VALUE not in result.stderr, "a frame local leaked a resolved secret"
    assert VALUE not in result.stdout


def test_the_same_value_does_reach_a_healthy_child(tmp_path: Path) -> None:
    """The probe above is only meaningful if this value is really resolved."""
    (tmp_path / ".env").write_text(f"SUPER={VALUE}\n")
    (tmp_path / "refs.env").write_text("A=dotenv://.env#SUPER\n")
    result = _ksecret(
        "run", "--env-file", "refs.env", "--",
        sys.executable, "-c", "import os;print(os.environ['A'])",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == VALUE


def test_an_env_file_is_read_as_utf8_under_a_non_utf8_locale(
    tmp_path: Path,
) -> None:
    """`read_text()` without an encoding follows the locale, not the promise.

    Only a real non-UTF-8 environment distinguishes the two, so this runs the
    console script with the C locale and Python's UTF-8 mode off.
    """
    accented = "caf\u00e9-\u00fcber"
    (tmp_path / ".env").write_text(f"K={accented}\n", encoding="utf-8")

    env = os.environ.copy()
    env.update(LC_ALL="C", LANG="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0")
    result = subprocess.run(
        ["uv", "run", "--project", str(ROOT), "ksecret",
         "read", "--print", "--no-newline", "dotenv://.env#K"],
        cwd=tmp_path, env=env, capture_output=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stdout.decode("utf-8") == accented, "read as UTF-8, written as UTF-8"


def test_a_check_error_line_survives_a_non_utf8_locale(tmp_path: Path) -> None:
    """The em dash in a check line is not the operator's codec's business."""
    (tmp_path / ".env").write_text("K=v\n")
    (tmp_path / "refs.env").write_text("BAD=dotenv://.env#NOPE\n")

    env = os.environ.copy()
    env.update(LC_ALL="C", LANG="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0")
    result = subprocess.run(
        ["uv", "run", "--project", str(ROOT), "ksecret",
         "check", "--env-file", "refs.env"],
        cwd=tmp_path, env=env, capture_output=True, timeout=120,
    )
    assert result.returncode == 1, result.stderr.decode("utf-8", "replace")
    out = result.stdout.decode("utf-8")
    assert out.startswith("BAD: error")
    assert "Traceback" not in result.stderr.decode("utf-8", "replace")


def _ksecret(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--project", str(ROOT), "ksecret", *args],
        cwd=cwd,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
    )
