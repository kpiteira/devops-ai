"""Acceptance fixtures for the secret-providers feature.

Planner-authored (spec/secret-providers). The surface under test is the `ksecret`
console script and kinfra's sandbox provisioning; both are exercised for real —
subprocesses, real files, real containers. Nothing here is mocked.
"""

from __future__ import annotations

import json
import os
import secrets as _secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

# Re-export the throwaway-project fixture so the kinfra-path test can use it. The
# e2e suite's autouse image pull is deliberately NOT re-exported: only the sandbox
# test needs Docker (see `sandbox_image`).
from tests.e2e.conftest import e2e_project  # noqa: F401

ROOT = Path(__file__).resolve().parents[3]
README = ROOT / "README.md"
# Seconds to wait for Karl to grant a 1Password access prompt (A3).
OP_GRANT_WAIT = 60
# The acceptance vault Karl created for these tests. Never gate on `op whoami`: it
# exits 1 on Karl's machine while `op` is fully usable (divergence M1-2026-09-12).
OP_VAULT_DEFAULT = "devops-ai-secrets-test"


@dataclass
class Result:
    code: int
    out: str
    err: str


def ksecret(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    timeout: int = 60,
) -> Result:
    """Run the real `ksecret` console script via uv, from `cwd`."""
    proc = subprocess.run(
        ["uv", "run", "--project", str(ROOT), "ksecret", *args],
        cwd=cwd or ROOT,
        env=env if env is not None else os.environ.copy(),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return Result(proc.returncode, proc.stdout, proc.stderr)


def clean_env(**overrides: str) -> dict[str, str]:
    """A copy of the environment with the test's variables controlled."""
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("KSECRET_T_"):
            del env[key]
    env.update(overrides)
    return env


def python_cmd(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture()
def sandbox_image() -> None:
    """Docker running and python:3.12-slim present.

    Only the kinfra sandbox test requests this.
    """
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("Docker is not running")
    subprocess.run(
        ["docker", "pull", "python:3.12-slim"], capture_output=True, timeout=300
    )


# ---------------------------------------------------------------- 1Password


def op_vault() -> str:
    """The 1Password acceptance vault, proven reachable by a real query — or skip.

    Access is proven the only way `op` allows: by querying the vault (A3). The query
    is the access prompt; it waits `OP_GRANT_WAIT` seconds for the touch. A missing
    CLI, a timeout, or a non-zero exit (no grant, or the vault does not exist) skips
    with the reason. `KSECRET_ACCEPTANCE_OP_VAULT` overrides the vault name.
    """
    vault = os.environ.get("KSECRET_ACCEPTANCE_OP_VAULT", OP_VAULT_DEFAULT)
    try:
        listed = subprocess.run(
            ["op", "item", "list", "--vault", vault, "--format=json"],
            capture_output=True, text=True, timeout=OP_GRANT_WAIT,
        )
    except FileNotFoundError:
        pytest.skip("1Password CLI not installed")
    except subprocess.TimeoutExpired:
        pytest.skip(f"1Password access not granted within {OP_GRANT_WAIT}s")
    if listed.returncode != 0:
        pytest.skip(
            f"1Password vault {vault!r} not accessible: {listed.stderr.strip()}"
        )
    return vault


@pytest.fixture()
def op_item() -> Iterator[tuple[str, str]]:
    """A fresh 1Password item with a generated password; skips if access isn't granted.

    There is no scriptable sign-in for `op`: it prompts the human per access. The
    fixture attempts access and waits long enough for a touch (A3). Yields
    (reference, expected_value); the value is obtained through `op read`, never
    placed in argv by the test.
    """
    vault = op_vault()
    title = f"ksecret-acceptance-{_secrets.token_hex(4)}"
    created = subprocess.run(
        [
            "op", "item", "create", "--vault", vault, "--category", "password",
            "--title", title, "--generate-password", "--format=json",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if created.returncode != 0:
        pytest.skip(f"could not create a 1Password item in vault {vault!r}")
    item_id = json.loads(created.stdout)["id"]
    ref = f"op://{vault}/{item_id}/password"
    try:
        expected = subprocess.run(
            ["op", "read", "--no-newline", ref],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
        yield ref, expected
    finally:
        subprocess.run(
            ["op", "item", "delete", item_id, "--vault", vault],
            capture_output=True, text=True, timeout=30,
        )


# ------------------------------------------------------------------ OpenBao


@dataclass
class BaoServer:
    addr: str
    token: str

    def write(self, mount: str, path: str, data: dict[str, str]) -> None:
        self._request("POST", f"/v1/{mount}/data/{path}", {"data": data})

    def read(self, mount: str, path: str) -> dict[str, str]:
        body = self._request("GET", f"/v1/{mount}/data/{path}")
        return dict(body["data"]["data"])

    def _request(self, method: str, api_path: str, payload: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.addr + api_path,
            method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"X-Vault-Token": self.token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else {}


@pytest.fixture(scope="module")
def bao() -> Iterator[BaoServer]:
    """A dev-mode OpenBao container: KV v2 at `secret/`, fixed root token."""
    docker = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if docker.returncode != 0:
        pytest.skip("Docker is not running")
    port = free_port()
    token = "ksecret-root-" + _secrets.token_hex(4)
    name = f"ksecret-acceptance-bao-{port}"
    run = subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            "-e", f"BAO_DEV_ROOT_TOKEN_ID={token}",
            "-p", f"127.0.0.1:{port}:8200",
            "openbao/openbao:2.5.4", "server", "-dev",
        ],
        capture_output=True, text=True, timeout=120,
    )
    if run.returncode != 0:
        pytest.skip(f"could not start openbao container: {run.stderr.strip()}")
    server = BaoServer(addr=f"http://127.0.0.1:{port}", token=token)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(server.addr + "/v1/sys/health", timeout=3):
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        else:
            pytest.fail("openbao dev server never became healthy")
        yield server
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)


# ---------------------------------------------------------- Azure Key Vault


@dataclass
class AkvVault:
    name: str

    def set(self, secret: str, value: str, tmp: Path) -> str:
        """Set a value (new version if the secret exists); returns the version id."""
        f = tmp / f"{secret}.value"
        f.write_text(value)
        f.chmod(0o600)
        out = subprocess.run(
            ["az", "keyvault", "secret", "set", "--vault-name", self.name,
             "--name", secret, "--file", str(f), "--query", "id", "-o", "tsv"],
            capture_output=True, text=True, timeout=120, check=True,
        ).stdout.strip()
        f.unlink()
        return out.rstrip("/").rsplit("/", 1)[-1]

    def delete(self, secret: str) -> None:
        subprocess.run(
            ["az", "keyvault", "secret", "delete", "--vault-name", self.name,
             "--name", secret, "--output", "none"],
            capture_output=True, text=True, timeout=120,
        )


@pytest.fixture(scope="module")
def akv() -> AkvVault:
    """The real acceptance Key Vault.

    Skips unless az is logged in and KSECRET_ACCEPTANCE_AKV_VAULT is set.
    """
    name = os.environ.get("KSECRET_ACCEPTANCE_AKV_VAULT")
    if not name:
        pytest.skip("KSECRET_ACCEPTANCE_AKV_VAULT is not set")
    try:
        acct = subprocess.run(
            ["az", "account", "show", "--output", "none"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("az CLI not installed")
    if acct.returncode != 0:
        pytest.skip("az is not logged in")
    return AkvVault(name=name)


def fresh_name(prefix: str) -> str:
    return f"{prefix}-{_secrets.token_hex(4)}"
