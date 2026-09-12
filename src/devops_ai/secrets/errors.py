"""Failures raised while resolving a secret reference.

Messages are user-facing and must never contain a secret value — only the
reference, the variable name, and what to do about it. A provider raises
`ProviderError` with the reason alone; the resolver knows which key was being
resolved and labels it.
"""

from __future__ import annotations


class ProviderError(Exception):
    """A provider could not resolve a reference. Carries the reason, unlabelled."""


class SecretResolutionError(Exception):
    """Secret resolution failure with actionable guidance."""

    def __init__(self, var_name: str, ref: str, message: str) -> None:
        self.var_name = var_name
        self.ref = ref
        self.message = message
        super().__init__(message)
