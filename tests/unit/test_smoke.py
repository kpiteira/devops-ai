"""Smoke tests for devops-ai package (import only, no subprocess)."""


def test_import():
    """Verify the devops_ai package can be imported."""
    import devops_ai  # noqa: F401
