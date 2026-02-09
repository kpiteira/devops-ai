"""Smoke tests for devops-ai package and kinfra CLI."""

import subprocess
import sys


def test_import():
    """Verify the devops_ai package can be imported."""
    import devops_ai  # noqa: F401


def test_cli_help():
    """Verify kinfra --help returns 0 and contains 'kinfra'."""
    result = subprocess.run(
        [sys.executable, "-m", "devops_ai.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "kinfra" in result.stdout.lower() or "kinfra" in result.stderr.lower()
