"""M4 — write (optional). Planner-authored; read-only for executors."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from tests.acceptance.secret_providers.conftest import (
    OP_GRANT_WAIT,
    AkvVault,
    BaoServer,
    clean_env,
    fresh_name,
    ksecret,
)

VALUE = "written-value-3b7e"


def test_write_then_read_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text("KEEP=untouched\nTARGET=old\n")
    r = ksecret(
        "write",
        "dotenv://secrets.env#TARGET",
        cwd=tmp_path,
        env=clean_env(),
        stdin=VALUE + "\n"
    )
    assert r.code == 0, r.err
    assert r.out == ""
    lines = env_file.read_text().splitlines()
    assert "KEEP=untouched" in lines
    assert sum(1 for ln in lines if ln.startswith("TARGET=")) == 1

    r = ksecret(
        "read", "--print",
        "--no-newline",
        "dotenv://secrets.env#TARGET",
        cwd=tmp_path,
        env=clean_env()
    )
    assert (r.code, r.out) == (0, VALUE), r.err

    # a fresh file is created 0600
    r = ksecret(
        "write", "dotenv://new.env#K", cwd=tmp_path, env=clean_env(), stdin=VALUE
    )
    assert r.code == 0, r.err
    new = tmp_path / "new.env"
    assert stat.S_IMODE(os.stat(new).st_mode) == 0o600
    r = ksecret(
        "read",
        "--print",
        "--no-newline",
        "dotenv://new.env#K",
        cwd=tmp_path,
        env=clean_env()
    )
    assert (r.code, r.out) == (0, VALUE)


def test_write_then_read_openbao(bao: BaoServer, tmp_path: Path) -> None:
    path = fresh_name("apps/ksecret-write")
    bao.write("secret", path, {"sibling": "must-survive"})
    env = clean_env(BAO_ADDR=bao.addr, BAO_TOKEN=bao.token)
    r = ksecret(
        "write", f"bao://secret/{path}#token", cwd=tmp_path, env=env, stdin=VALUE
    )
    assert r.code == 0, r.err
    assert bao.read("secret", path) == {"sibling": "must-survive", "token": VALUE}
    r = ksecret(
        "read",
        "--print",
        "--no-newline",
        f"bao://secret/{path}#token",
        cwd=tmp_path,
        env=env
    )
    assert (r.code, r.out) == (0, VALUE), r.err


def test_write_then_read_akv(akv: AkvVault, tmp_path: Path) -> None:
    name = fresh_name("ksecret-acceptance-write")
    try:
        r = ksecret(
            "write",
            f"akv://{akv.name}/{name}",
            cwd=tmp_path,
            env=clean_env(),
            stdin=VALUE
        )
        assert r.code == 0, r.err
        r = ksecret(
            "read", "--print",
            "--no-newline",
            f"akv://{akv.name}/{name}",
            cwd=tmp_path,
            env=clean_env()
        )
        assert (r.code, r.out) == (0, VALUE), r.err
    finally:
        akv.delete(name)


def test_write_op_creates_and_updates_item(tmp_path: Path) -> None:
    try:
        who = subprocess.run(
            ["op", "whoami"], capture_output=True, text=True, timeout=OP_GRANT_WAIT
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("1Password CLI not installed, or access not granted in time")
    if who.returncode != 0:
        pytest.skip("1Password access not granted")
    vault = os.environ.get("KSECRET_ACCEPTANCE_OP_VAULT", "Private")
    title = fresh_name("ksecret-acceptance-write")
    ref = f"op://{vault}/{title}/password"
    try:
        r = ksecret("write", ref, cwd=tmp_path, env=clean_env(), stdin=VALUE)
        assert r.code == 0, r.err
        r = ksecret(
            "read",
            "--print",
            "--no-newline",
            ref,
            cwd=tmp_path,
            env=clean_env(),
        )
        assert (r.code, r.out) == (0, VALUE), r.err
        # second write to the same reference updates the field in place
        r = ksecret("write", ref, cwd=tmp_path, env=clean_env(), stdin=VALUE + "-v2")
        assert r.code == 0, r.err
        r = ksecret(
            "read",
            "--print",
            "--no-newline",
            ref,
            cwd=tmp_path,
            env=clean_env(),
        )
        assert (r.code, r.out) == (0, VALUE + "-v2"), r.err
    finally:
        listed = subprocess.run(
            ["op", "item", "list", "--vault", vault, "--format=json"],
            capture_output=True, text=True, timeout=30,
        )
        if listed.returncode == 0:
            for item in json.loads(listed.stdout):
                if item.get("title") == title:
                    subprocess.run(
                        ["op", "item", "delete", item["id"], "--vault", vault],
                        capture_output=True, text=True, timeout=30,
                    )


def test_write_env_is_refused(tmp_path: Path) -> None:
    r = ksecret(
        "write",
        "env://KSECRET_T_X",
        cwd=tmp_path,
        env=clean_env(),
        stdin=VALUE,
    )
    assert r.code == 1 and r.out == ""
    assert "read-only" in r.err.lower() or "cannot" in r.err.lower()
    assert VALUE not in r.err
