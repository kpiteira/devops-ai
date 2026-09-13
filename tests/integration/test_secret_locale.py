"""Encoding promises hold under a non-UTF-8 locale.

`monkeypatch.setenv("LC_ALL", "C")` cannot test any of this: the process locale is
fixed at interpreter start, so an in-process test passes whether or not the code
names an encoding. Only a real child process in a real C locale tells them apart —
which is why these live here rather than in `tests/unit/`.

The environment is the point: `kinfra impl` and `ksecret run` are meant to run in
containers, cron and CI, where `LC_ALL=C` is ordinary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACCENTED = "café-über"


@pytest.fixture()
def c_locale() -> dict[str, str]:
    env = os.environ.copy()
    env.update(LC_ALL="C", LANG="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0")
    return env


def run_child(
    code: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--project", str(ROOT), "python", "-c", code],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=300,
    )


def test_a_non_ascii_repo_path_is_decoded_not_crashed_on(
    tmp_path: Path, c_locale: dict[str, str]
) -> None:
    """A path is bytes; `git rev-parse` emits them raw and the locale is no codec."""
    repo = tmp_path / "caf\u00e9-repo"
    repo.mkdir()
    for args in (["git", "init", "-q", "."], ["git", "config", "user.email", "t@t"],
                 ["git", "config", "user.name", "T"]):
        subprocess.run(args, cwd=repo, check=True, capture_output=True)

    result = run_child(
        "import os, sys\n"
        "from pathlib import Path\n"
        "from devops_ai.worktree import main_repo_root\n"
        f"r = main_repo_root(Path(os.fsdecode({os.fsencode(repo)!r})))\n"
        "sys.stdout.buffer.write(os.fsencode(r) if r else b'None')",
        c_locale, tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.encode("utf-8", "surrogateescape") == os.fsencode(repo)


def test_the_materialised_secrets_file_is_written_as_utf8(
    tmp_path: Path, c_locale: dict[str, str]
) -> None:
    """kinfra provisioning must not die on a non-ASCII secret."""
    result = run_child(
        "from pathlib import Path\n"
        "from devops_ai.provision import generate_secrets_file\n"
        f"generate_secrets_file({{'K': {ACCENTED!r}}}, Path({str(tmp_path)!r}))\n"
        "print('wrote')",
        c_locale, tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".env.secrets").read_bytes() == f"K={ACCENTED}\n".encode()


def test_a_materialised_utf8_file_is_still_readable_for_reuse(
    tmp_path: Path, c_locale: dict[str, str]
) -> None:
    """Otherwise the C locale forces a re-resolve — the keychain prompt REUSE avoids."""
    (tmp_path / ".env.secrets").write_bytes(f"K={ACCENTED}\n".encode())
    result = run_child(
        "from pathlib import Path\n"
        "from devops_ai.cli.sandbox_cmd import plan_secrets\n"
        f"slot = Path({str(tmp_path)!r})\n"
        "print(plan_secrets({'K': 'literal'}, slot, refresh=False).value)",
        c_locale, tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "reuse", "a readable file was treated as unreadable"


def test_a_non_ascii_secret_from_op_survives(
    tmp_path: Path, c_locale: dict[str, str]
) -> None:
    """`op` returns bytes; the operator's codec is not the secret's encoding."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "op"
    fake.write_bytes(f'#!/bin/sh\nprintf %s {ACCENTED!r}\n'.encode())
    fake.chmod(0o755)

    result = run_child(
        "import sys\n"
        "from devops_ai.secrets import ResolveContext, resolve\n"
        f"ctx = ResolveContext(env={{'PATH': {str(bin_dir)!r}}})\n"
        "v = resolve('K', 'op://v/i/f', ctx)\n"
        "sys.stdout.buffer.write(v.encode('utf-8'))",
        c_locale, tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ACCENTED


def test_a_non_ascii_secret_from_akv_survives(
    tmp_path: Path, c_locale: dict[str, str]
) -> None:
    """`az` returns bytes too — JSON output does not make the operator's codec safe.

    The escape hatch that hides this: `json.dumps` defaults to `ensure_ascii=True`,
    so a fake `az` built from it emits pure ASCII and would pass under any codec.
    This one writes the raw UTF-8 bytes a real vault returns.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "az"
    encoded = json.dumps(ACCENTED, ensure_ascii=False)
    fake.write_bytes(f"#!/bin/sh\nprintf %s {encoded!r}\n".encode())
    fake.chmod(0o755)

    result = run_child(
        "import sys\n"
        "from devops_ai.secrets import ResolveContext, resolve\n"
        f"ctx = ResolveContext(env={{'PATH': {str(bin_dir)!r}}})\n"
        "v = resolve('K', 'akv://a-vault/a-secret', ctx)\n"
        "sys.stdout.buffer.write(v.encode('utf-8'))",
        c_locale, tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ACCENTED


def test_ksecret_run_passes_a_non_ascii_value_to_its_child(
    tmp_path: Path, c_locale: dict[str, str]
) -> None:
    """End to end: the value reaches the child intact, under C."""
    (tmp_path / ".env").write_text(f"K={ACCENTED}\n", encoding="utf-8")
    (tmp_path / "refs.env").write_text("A=dotenv://.env#K\n")
    result = subprocess.run(
        ["uv", "run", "--project", str(ROOT), "ksecret",
         "run", "--env-file", "refs.env", "--",
         sys.executable, "-c",
         "import os,sys;sys.stdout.buffer.write(os.environb[b'A'])"],
        cwd=tmp_path, env=c_locale, capture_output=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stdout.decode("utf-8") == ACCENTED
