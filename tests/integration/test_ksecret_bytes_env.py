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

import os
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


def _ksecret(
    *args: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--project", str(ROOT), "ksecret", *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=300,
    )


def _probe(project: Path) -> Path:
    """A program reachable *only* through PATH, never through `os.defpath`.

    `env` or `echo` would not do. `os.get_exec_path` falls back to `os.defpath`
    (`:/bin:/usr/bin`) when it finds no PATH at all, so a command living there
    is found whether or not the bytes key was ever read — the test would pass
    identically in the broken and the healthy case.
    """
    bin_dir = project / "bin"
    bin_dir.mkdir()
    program = bin_dir / "ksecret-path-probe"
    program.write_text('#!/bin/sh\nprintf %s "$A"\n')
    program.chmod(0o755)
    return program


def _env_reaching(bin_dir: Path | None) -> dict[str, str]:
    """The caller's environment, optionally with `bin_dir` ahead of it.

    PATH is otherwise left whole: emptying it would strand the outer `uv`
    rather than the child, which is not the lookup under test.
    """
    env = os.environ.copy()
    if bin_dir is not None:
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return env


def test_a_bare_command_name_is_still_found_on_path(project: Path) -> None:
    """The child is found by name, and the resolved value reaches it."""
    program = _probe(project)
    result = _ksecret(
        "run", "--env-file", "refs.env", "--", program.name,
        cwd=project, env=_env_reaching(program.parent),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == VALUE


def test_the_probe_is_unreachable_when_path_does_not_name_it(
    project: Path,
) -> None:
    """The control: the test above passes because of PATH, nothing else."""
    program = _probe(project)
    result = _ksecret(
        "run", "--env-file", "refs.env", "--", program.name,
        cwd=project, env=_env_reaching(None),
    )
    assert result.returncode == 127, result.stdout


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
