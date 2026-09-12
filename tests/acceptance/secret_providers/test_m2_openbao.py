"""M2 — OpenBao provider. Planner-authored; read-only for executors."""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.secret_providers.conftest import (
    README,
    BaoServer,
    clean_env,
    fresh_name,
    ksecret,
    python_cmd,
)

VALUE = "bao-secret-value-4e2b"
OTHER = "other-key-value-1a9f"


def test_read_kv2_secret_from_dev_server(bao: BaoServer, tmp_path: Path) -> None:
    path = fresh_name("apps/ksecret")
    bao.write("secret", path, {"token": VALUE, "other": OTHER})
    # BAO_* wins over conflicting VAULT_* spellings
    env = clean_env(
        BAO_ADDR=bao.addr, BAO_TOKEN=bao.token,
        VAULT_ADDR="http://127.0.0.1:9", VAULT_TOKEN="wrong-token",
    )

    r = ksecret(
        "read",
        "--print",
        "--no-newline",
        f"bao://secret/{path}#token",
        cwd=tmp_path,
        env=env
    )
    assert (r.code, r.out) == (0, VALUE), r.err

    # VAULT_* spelling is honored too
    env_v = clean_env(VAULT_ADDR=bao.addr, VAULT_TOKEN=bao.token)
    env_v.pop("BAO_ADDR", None)
    env_v.pop("BAO_TOKEN", None)
    r = ksecret(
        "read",
        "--print",
        "--no-newline",
        f"bao://secret/{path}#token",
        cwd=tmp_path,
        env=env_v
    )
    assert (r.code, r.out) == (0, VALUE), r.err


def test_token_file_fallback_and_missing_key(bao: BaoServer, tmp_path: Path) -> None:
    path = fresh_name("apps/ksecret")
    bao.write("secret", path, {"token": VALUE, "other": OTHER})
    home = tmp_path / "home"
    home.mkdir()
    (home / ".vault-token").write_text(bao.token)
    env = clean_env(BAO_ADDR=bao.addr, HOME=str(home))
    for k in ("BAO_TOKEN", "VAULT_TOKEN", "VAULT_ADDR"):
        env.pop(k, None)

    # precedence: an env token beats the file, and BAO_TOKEN beats VAULT_TOKEN
    (tmp_path / "wrong-home").mkdir()
    (tmp_path / "wrong-home" / ".vault-token").write_text("wrong-file-token")
    env_prec = clean_env(
        BAO_ADDR=bao.addr, BAO_TOKEN=bao.token, VAULT_TOKEN="wrong-token",
        HOME=str(tmp_path / "wrong-home"),
    )
    r = ksecret(
        "read", "--print", "--no-newline", f"bao://secret/{path}#token",
        cwd=tmp_path, env=env_prec,
    )
    assert (r.code, r.out) == (0, VALUE), r.err

    r = ksecret(
        "read",
        "--print",
        "--no-newline",
        f"bao://secret/{path}#token",
        cwd=tmp_path,
        env=env
    )
    assert (r.code, r.out) == (0, VALUE), r.err

    r = ksecret(
        "read",
        "--print",
        f"bao://secret/{path}#missing",
        cwd=tmp_path,
        env=env,
    )
    assert r.code == 1 and r.out == ""
    assert "missing" in r.err
    assert VALUE not in r.err and OTHER not in r.err, "no sibling value may leak"

    # a reference without #key is an error, and leaks nothing
    r = ksecret("read", f"bao://secret/{path}", cwd=tmp_path, env=env)
    assert r.code == 1 and r.out == ""
    assert VALUE not in r.err and OTHER not in r.err

    # no token anywhere → guidance, no crash
    env_no = clean_env(BAO_ADDR=bao.addr, HOME=str(tmp_path / "empty-home"))
    for k in ("BAO_TOKEN", "VAULT_TOKEN", "VAULT_ADDR"):
        env_no.pop(k, None)
    r = ksecret(
        "read",
        "--print",
        f"bao://secret/{path}#token",
        cwd=tmp_path,
        env=env_no,
    )
    assert r.code == 1 and r.out == ""
    assert "token" in r.err.lower()


def test_run_and_check_accept_bao_refs(bao: BaoServer, tmp_path: Path) -> None:
    path = fresh_name("apps/ksecret")
    bao.write("secret", path, {"token": VALUE})
    (tmp_path / "refs.env").write_text(f"T=bao://secret/{path}#token\n")
    env = clean_env(BAO_ADDR=bao.addr, BAO_TOKEN=bao.token)

    r = ksecret(
        "run", "--env-file", "refs.env", "--",
        *python_cmd("import os; print(os.environ['T'])"),
        cwd=tmp_path, env=env,
    )
    assert (r.code, r.out.strip()) == (0, VALUE), r.err

    r = ksecret("check", "--env-file", "refs.env", cwd=tmp_path, env=env)
    assert r.code == 0, r.err
    assert "ok" in r.out and VALUE not in r.out


def test_bao_is_a_provider_module() -> None:
    """The scheme is owned by exactly one provider module, not by the resolver."""
    from tests.architecture.test_secret_providers import provider_modules, schemes_in

    owners = [m.name for m in provider_modules() if "bao://" in schemes_in(m)]
    assert len(owners) == 1, owners


def test_readme_documents_bao() -> None:
    text = README.read_text()
    for needle in ("bao://", "BAO_ADDR", "BAO_TOKEN", ".vault-token"):
        assert needle in text, f"README must document {needle}"
