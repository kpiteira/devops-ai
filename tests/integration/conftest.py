"""Integration fixtures — the Docker guard shared by tests that reach the daemon.

Several tests here drive ``impl_command``, which calls
``ObservabilityManager.ensure_network()`` and so needs a reachable Docker daemon.
Without a guard they fail on a bare ``assert 1 == 0`` over the exit code, which reads
as "I broke something" rather than "Docker is off" (issue #37). The guard is the one
``tests/e2e/conftest.py`` and the secret-providers acceptance conftest already use:
ask ``docker info``, and skip only when it does not answer.
"""

from __future__ import annotations

import subprocess

import pytest

# Generous on purpose: a cold Docker Desktop answers slowly, and a skip fired at a
# daemon that is merely slow would hide real failures.
DOCKER_INFO_TIMEOUT = 30


def docker_unavailable_reason() -> str | None:
    """Why the Docker daemon cannot be reached, or ``None`` when it answers.

    Only an unreachable daemon produces a reason. A successful ``docker info``
    returns ``None``, so whatever the test does next is judged on its own merits —
    the guard can never turn a broken test into a skip.
    """
    try:
        probe = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=DOCKER_INFO_TIMEOUT,
        )
    except FileNotFoundError:
        return "Docker is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return (
            "Docker daemon did not answer `docker info` within "
            f"{DOCKER_INFO_TIMEOUT}s"
        )
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip().splitlines()
        tail = detail[-1].strip() if detail else f"exit {probe.returncode}"
        return f"Docker is not running (`docker info`: {tail})"
    return None


@pytest.fixture(scope="session")
def docker_running() -> None:
    """Skip the requesting test when the Docker daemon is unreachable.

    Session-scoped so the probe runs once per suite, not once per test.
    """
    reason = docker_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)
