"""M3 — Azure Key Vault provider. Planner-authored; read-only for executors.

Runs against the real acceptance vault named by KSECRET_ACCEPTANCE_AKV_VAULT and
skips otherwise (no local AKV runtime exists).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.acceptance.secret_providers.conftest import (
    README,
    AkvVault,
    clean_env,
    fresh_name,
    ksecret,
    python_cmd,
)

VALUE = "akv-secret-value-6d0c"


@pytest.fixture()
def akv_secret(akv: AkvVault, tmp_path: Path) -> Iterator[tuple[str, str]]:
    name = fresh_name("ksecret-acceptance")
    akv.set(name, VALUE, tmp_path)
    try:
        yield f"akv://{akv.name}/{name}", VALUE
    finally:
        akv.delete(name)


def test_read_secret_from_real_vault(
    akv_secret: tuple[str, str], tmp_path: Path
) -> None:
    ref, expected = akv_secret
    r = ksecret("read", "--print", "--no-newline", ref, cwd=tmp_path, env=clean_env())
    assert (r.code, r.out) == (0, expected), r.err


def test_versioned_reference_reads_that_version(akv: AkvVault, tmp_path: Path) -> None:
    name = fresh_name("ksecret-acceptance-versions")
    try:
        v1 = akv.set(name, VALUE + "-v1", tmp_path)
        akv.set(name, VALUE + "-v2", tmp_path)
        env = clean_env()
        r = ksecret(
            "read",
            "--print",
            "--no-newline",
            f"akv://{akv.name}/{name}",
            cwd=tmp_path,
            env=env,
        )
        assert (r.code, r.out) == (0, VALUE + "-v2"), r.err
        r = ksecret(
            "read",
            "--print",
            "--no-newline",
            f"akv://{akv.name}/{name}/{v1}",
            cwd=tmp_path,
            env=env,
        )
        assert (r.code, r.out) == (0, VALUE + "-v1"), r.err
    finally:
        akv.delete(name)


def test_missing_secret_names_ref_not_value(akv: AkvVault, tmp_path: Path) -> None:
    missing = fresh_name("ksecret-acceptance-missing")
    r = ksecret(
        "read",
        "--print",
        f"akv://{akv.name}/{missing}",
        cwd=tmp_path,
        env=clean_env(),
    )
    assert r.code == 1 and r.out == ""
    assert missing in r.err
    assert "not found" in r.err.lower()


def test_run_and_check_accept_akv_refs(
    akv_secret: tuple[str, str], tmp_path: Path
) -> None:
    ref, expected = akv_secret
    (tmp_path / "refs.env").write_text(f"T={ref}\n")
    r = ksecret(
        "run", "--env-file", "refs.env", "--",
        *python_cmd("import os; print(os.environ['T'])"),
        cwd=tmp_path, env=clean_env(),
    )
    assert (r.code, r.out.strip()) == (0, expected), r.err

    r = ksecret("check", "--env-file", "refs.env", cwd=tmp_path, env=clean_env())
    assert r.code == 0, r.err
    assert "ok" in r.out and expected not in r.out


def test_akv_is_a_provider_module() -> None:
    """The scheme is owned by exactly one provider module, not by the resolver."""
    from tests.architecture.test_secret_providers import provider_modules, schemes_in

    owners = [m.name for m in provider_modules() if "akv://" in schemes_in(m)]
    assert len(owners) == 1, owners


def test_readme_documents_akv() -> None:
    text = README.read_text()
    assert "akv://" in text
    assert "az login" in text
