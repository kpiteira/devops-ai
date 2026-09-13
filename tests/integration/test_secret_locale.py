"""Encoding promises hold under a non-UTF-8 locale.

`monkeypatch.setenv("LC_ALL", "C")` cannot test any of this: the process locale is
fixed at interpreter start, so an in-process test passes whether or not the code
names an encoding. Only a real child process in a real C locale tells them apart —
which is why these live here rather than in `tests/unit/`.

The environment is the point: `kinfra impl` and `ksecret run` are meant to run in
containers, cron and CI, where `LC_ALL=C` is ordinary.

A real child is necessary but not sufficient: macOS hardcodes the filesystem
encoding to UTF-8 whatever `LC_ALL` says, so the fixture below changed nothing
on any developer machine and every test here was vacuously green until CI first
ran them on Linux (#58). They now skip where the C locale is inert, so a green
means the fixture bit.
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
# What a C locale gives a child anywhere but macOS, and so the one condition
# every test in this file actually depends on.
ASCII_FSENCODING = "ascii"

# Prepended to every child: the same promise the fixture skips on, restated
# where it has to hold — inside the child, ahead of the code under test.
PRECONDITION = (
    "import sys\n"
    "assert sys.getfilesystemencoding() == 'ascii', (\n"
    "    'the C-locale fixture is inert: ' + sys.getfilesystemencoding())\n"
)


@pytest.fixture(scope="session")
def c_locale_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(LC_ALL="C", LANG="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0")
    return env


@pytest.fixture(scope="session")
def child_fsencoding(c_locale_env: dict[str, str]) -> str:
    """What the fixture really produces here, asked once of a real child.

    The parent cannot answer: its own filesystem encoding is fixed at
    interpreter start and is not the one the fixture would give a child.
    """
    result = subprocess.run(
        ["uv", "run", "--project", str(ROOT), "python", "-c",
         "import sys; print(sys.getfilesystemencoding())"],
        cwd=ROOT, env=c_locale_env, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(f"could not probe the child's encoding: {result.stderr}")
    return result.stdout.strip()


@pytest.fixture()
def c_locale(
    c_locale_env: dict[str, str], child_fsencoding: str
) -> dict[str, str]:
    """A C locale, or a skip where the platform declines to give one.

    Skipping, never xfail: there is nothing here to expect a failure from. The
    tests are right and the platform simply cannot run them.
    """
    if child_fsencoding != ASCII_FSENCODING:
        pytest.skip(
            f"the C locale is inert on this platform: a child under LC_ALL=C "
            f"reports filesystem encoding {child_fsencoding!r}, not "
            f"{ASCII_FSENCODING!r}, so nothing here would be exercised"
        )
    return dict(c_locale_env)


def run_child(
    code: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--project", str(ROOT), "python", "-c",
         PRECONDITION + code],
        cwd=cwd, env=env, capture_output=True, timeout=300,
        # Not a bare `text=True`: that decodes the child's stdout with the
        # *parent's* locale codec, so running pytest itself under `LC_ALL=C`
        # broke these on the accented bytes the child deliberately wrote —
        # the same defect as #58, one layer up, in the harness that proves it.
        # `surrogateescape` so any byte round-trips back out exactly.
        encoding="utf-8", errors="surrogateescape",
    )


def test_a_non_ascii_repo_path_is_decoded_not_crashed_on(
    tmp_path: Path, c_locale: dict[str, str]
) -> None:
    """A path is bytes; `git rev-parse` emits them raw and the locale is no codec.

    The directory is named in bytes rather than as a `str`. `Path.mkdir()` goes
    through `os.fsencode`, so when pytest *itself* runs under `LC_ALL=C` the
    parent cannot even create `café-repo` — it raises before the child under
    test is reached. Bytes are what the filesystem takes either way.
    """
    repo = os.fsencode(tmp_path) + "/café-repo".encode()
    os.mkdir(repo)
    for args in (["git", "init", "-q", "."], ["git", "config", "user.email", "t@t"],
                 ["git", "config", "user.name", "T"]):
        subprocess.run(args, cwd=repo, check=True, capture_output=True)

    result = run_child(
        "import os, sys\n"
        "from pathlib import Path\n"
        "from devops_ai.worktree import main_repo_root\n"
        f"r = main_repo_root(Path(os.fsdecode({repo!r})))\n"
        "sys.stdout.buffer.write(os.fsencode(r) if r else b'None')",
        c_locale, tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.encode("utf-8", "surrogateescape") == repo


def test_the_materialised_secrets_file_is_written_as_utf8(
    tmp_path: Path, c_locale: dict[str, str]
) -> None:
    """kinfra provisioning must not die on a non-ASCII secret.

    The value crosses as the repr of its UTF-8 bytes rather than as itself: an
    argv element is encoded with the filesystem encoding too, so an accented
    literal in the `python -c` source never reaches the child under an ASCII
    one — it dies decoding its own command line, before importing anything
    (#58). Its neighbours here already move it as bytes, through a file or an
    ASCII-safe repr; this one did not. Deliberately unnumbered: the issue
    numbered these and got it wrong, because the count drifts as tests are
    added.
    """
    result = run_child(
        "from pathlib import Path\n"
        "from devops_ai.provision import generate_secrets_file\n"
        f"value = {ACCENTED.encode()!r}.decode('utf-8')\n"
        f"generate_secrets_file({{'K': value}}, Path({str(tmp_path)!r}))\n"
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
