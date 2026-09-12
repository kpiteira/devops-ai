"""M1 — ksecret with env, dotenv, 1Password.

Planner-authored; read-only for executors.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from devops_ai.cli.impl import impl_command
from tests.acceptance.secret_providers.conftest import (
    README,
    clean_env,
    ksecret,
    python_cmd,
)

SECRET = "hello-from-dotenv-7f3a"
FALLBACK = "fallback-value-9c1d"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / ".env").write_text(
        "# comment line\n"
        f"FROM_DOTENV={SECRET}\n"
        f'QUOTED="{SECRET}"\n'
        f"KSECRET_T_FALLBACK={FALLBACK}\n"
        "\n"
    )
    return tmp_path


# ------------------------------------------------------------------- J1 read


def test_read_env_dotenv_and_literal(project: Path) -> None:
    env = clean_env(KSECRET_T_EXPORTED="exported-value-1")

    r = ksecret("read", "--print", "$KSECRET_T_EXPORTED", cwd=project, env=env)
    assert (r.code, r.out) == (0, "exported-value-1\n"), r.err

    r = ksecret(
        "read",
        "--print",
        "env://KSECRET_T_EXPORTED",
        "--no-newline",
        cwd=project,
        env=env
    )
    assert (r.code, r.out) == (0, "exported-value-1"), r.err

    r = ksecret("read", "--print", "dotenv://.env#FROM_DOTENV", cwd=project, env=env)
    assert (r.code, r.out) == (0, f"{SECRET}\n"), r.err

    r = ksecret("read", "--print", "dotenv://.env#QUOTED", cwd=project, env=env)
    assert (r.code, r.out) == (0, f"{SECRET}\n"), "quotes must be stripped"

    # $VAR not exported → falls back to ./.env
    r = ksecret("read", "--print", "$KSECRET_T_FALLBACK", cwd=project, env=env)
    assert (r.code, r.out) == (0, f"{FALLBACK}\n"), r.err

    r = ksecret("read", "--print", "env://KSECRET_T_FALLBACK", cwd=project, env=env)
    assert (r.code, r.out) == (0, f"{FALLBACK}\n"), "env:// falls back like $VAR"

    # exported wins over the file
    env2 = clean_env(KSECRET_T_FALLBACK="from-shell")
    r = ksecret("read", "--print", "$KSECRET_T_FALLBACK", cwd=project, env=env2)
    assert (r.code, r.out) == (0, "from-shell\n"), r.err

    # literals, including an unregistered scheme (A8)
    r = ksecret("read", "--print", "plain-literal", cwd=project, env=env)
    assert (r.code, r.out) == (0, "plain-literal\n"), r.err
    r = ksecret(
        "read",
        "--print",
        "postgres://dev:dev@db:5432/app",
        cwd=project,
        env=env,
    )
    assert (r.code, r.out) == (0, "postgres://dev:dev@db:5432/app\n"), r.err


def test_read_failure_names_ref_not_value(project: Path) -> None:
    env = clean_env()
    r = ksecret("read", "--print", "dotenv://.env#NOPE", cwd=project, env=env)
    assert r.code == 1
    assert r.out == ""
    assert "NOPE" in r.err and ".env" in r.err
    assert SECRET not in r.err

    r = ksecret("read", "--print", "$KSECRET_T_UNSET", cwd=project, env=env)
    assert r.code == 1 and r.out == ""
    assert "KSECRET_T_UNSET" in r.err


def test_read_without_print_confirms_only(project: Path) -> None:
    """Printing a secret is always explicit: a bare `read` confirms, never leaks."""
    r = ksecret("read", "dotenv://.env#FROM_DOTENV", cwd=project, env=clean_env())
    assert r.code == 0, r.err
    assert r.out.strip() == "ok dotenv://.env#FROM_DOTENV"
    assert SECRET not in r.out and SECRET not in r.err

    r = ksecret("read", "dotenv://.env#NOPE", cwd=project, env=clean_env())
    assert r.code == 1 and r.out == ""
    assert "NOPE" in r.err and SECRET not in r.err


def test_read_op_reference(op_item: tuple[str, str], tmp_path: Path) -> None:
    ref, expected = op_item
    r = ksecret("read", "--print", "--no-newline", ref, cwd=tmp_path)
    assert r.code == 0, r.err
    assert r.out == expected


# -------------------------------------------------------------------- J2 run


def test_run_injects_resolved_env_without_disk(project: Path) -> None:
    refs = project / "refs.env"
    refs.write_text(
        "# agent-memory style file\n"
        "OP_ACCOUNT=my-account.1password.com\n"
        "A=dotenv://.env#FROM_DOTENV\n"
        "B=$KSECRET_T_EXPORTED\n"
        "C=literal-c\n"
        "D=$OP_ACCOUNT\n"  # literal lines are in the environment before resolution
    )
    before = sorted(p.name for p in project.iterdir())
    env = clean_env(KSECRET_T_EXPORTED="exported-value-2", KSECRET_T_PARENT="parent")
    r = ksecret(
        "run", "--env-file", "refs.env", "--",
        *python_cmd(
            "import os,sys;"
            "print(os.environ['A'], os.environ['B'], os.environ['C'],"
            " os.environ['OP_ACCOUNT'], os.environ['KSECRET_T_PARENT'],"
            " os.environ['D']);"
            "sys.exit(7)"
        ),
        cwd=project, env=env,
    )
    assert r.code == 7, "child's exit code must propagate"
    assert r.out.strip() == (
        f"{SECRET} exported-value-2 literal-c my-account.1password.com parent"
        " my-account.1password.com"
    )
    after = sorted(p.name for p in project.iterdir())
    assert before == after, "run must write nothing to disk"


def test_run_refuses_when_any_ref_fails(project: Path) -> None:
    refs = project / "refs.env"
    refs.write_text("GOOD=dotenv://.env#FROM_DOTENV\nBAD=dotenv://.env#NOPE\n")
    marker = project / "ran.marker"
    r = ksecret(
        "run", "--env-file", "refs.env", "--",
        *python_cmd(f"open({str(marker)!r}, 'w').write('x')"),
        cwd=project, env=clean_env(),
    )
    assert r.code == 1
    assert not marker.exists(), "command must not run when a reference fails"
    assert "BAD" in r.err
    assert SECRET not in r.err and SECRET not in r.out


# ------------------------------------------------------------------ J3 check


def test_check_reports_without_values(project: Path) -> None:
    refs = project / "refs.env"
    refs.write_text(
        "A=dotenv://.env#FROM_DOTENV\n"
        "C=literal-c\n"
        "U=weird://not/registered\n"
        "BAD=dotenv://.env#NOPE\n"
    )
    r = ksecret("check", "--env-file", "refs.env", cwd=project, env=clean_env())
    assert r.code == 1
    lines = {ln.split(":")[0].strip(): ln for ln in r.out.splitlines() if ":" in ln}
    assert "ok" in lines["A"]
    assert "literal" in lines["C"]
    assert "literal" in lines["U"]
    assert "error" in lines["BAD"]
    assert SECRET not in r.out and SECRET not in r.err

    good = project / "good.env"
    good.write_text("A=dotenv://.env#FROM_DOTENV\nC=literal-c\n")
    r = ksecret("check", "--env-file", "good.env", cwd=project, env=clean_env())
    assert r.code == 0, r.err

    r = ksecret("check", "dotenv://.env#FROM_DOTENV", cwd=project, env=clean_env())
    assert r.code == 0 and "ok" in r.out and SECRET not in r.out


# ---------------------------------------------------------- J4 kinfra sandbox


def test_kinfra_sandbox_resolves_dotenv_and_env_fallback(
    sandbox_image: None, e2e_project: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    repo_root: Path = e2e_project["repo_root"]
    project_name: str = e2e_project["project_name"]

    # A newcomer's setup: gitignored .env in the main repo, refs in infra.toml.
    (repo_root / ".gitignore").write_text(".env\n")
    (repo_root / ".env").write_text(
        f"FROM_FILE={SECRET}\nKSECRET_T_FB={FALLBACK}\n"
    )
    infra = repo_root / ".devops-ai" / "infra.toml"
    infra.write_text(
        infra.read_text()
        + "\n[sandbox.secrets]\n"
        'FROM_FILE = "dotenv://.env#FROM_FILE"\n'
        'FB = "$KSECRET_T_FB"\n'
    )
    subprocess.run(
        ["git", "add", "-A"], cwd=repo_root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "secrets"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    monkeypatch.delenv("KSECRET_T_FB", raising=False)

    code, msg = impl_command("e2e-feat/M1", repo_root=repo_root)
    assert code == 0, msg
    assert SECRET not in msg and FALLBACK not in msg, "values must not be echoed"

    slot_dirs = list((Path.home() / ".devops-ai" / "slots").glob(f"{project_name}-*"))
    assert len(slot_dirs) == 1, slot_dirs
    secrets_file = slot_dirs[0] / ".env.secrets"
    assert secrets_file.exists()
    content = secrets_file.read_text()
    assert f"FROM_FILE={SECRET}\n" in content
    assert f"FB={FALLBACK}\n" in content
    assert stat.S_IMODE(os.stat(secrets_file).st_mode) == 0o600


# ------------------------------------------------------ provider package shape


def test_providers_package_is_in_place() -> None:
    """The architecture gate skips until this package exists; M1 must create it."""
    from tests.architecture.test_secret_providers import PROVIDERS, provider_modules

    assert PROVIDERS.is_dir(), "src/devops_ai/secrets/providers/ must exist"
    assert len(provider_modules()) >= 3, [m.name for m in provider_modules()]


# -------------------------------------------------------------------- J5 docs


def test_readme_documents_every_scheme() -> None:
    text = README.read_text()
    assert "## Secrets" in text or "# Secrets" in text
    for scheme in ("env://", "dotenv://", "op://", "bao://", "akv://"):
        assert scheme in text, f"README must document {scheme}"
    assert "--reinstall" in text, "README must say how to obtain the new command"
    assert "recommend" in text.lower(), "README carries the recommendation, not the CLI"
