"""Failures raised while resolving a secret reference.

Messages are user-facing and must never contain a secret value — only the
reference, the variable name, and what to do about it. A provider raises
`ProviderError` with the reason alone; the resolver knows which key was being
resolved and labels it.
"""

from __future__ import annotations


class ProviderError(Exception):
    """A provider could not resolve a reference. Carries the reason, unlabelled."""


class EnvironmentEncodingError(Exception):
    """A name or value cannot be encoded into a child's POSIX environment.

    Names the variable and never its value: the `UnicodeEncodeError` this
    replaces quotes the character it choked on, and for a resolved secret that
    character is part of the secret.
    """


class SecretResolutionError(Exception):
    """Secret resolution failure with actionable guidance.

    `message` is labelled with the key that failed and belongs on stderr;
    `reason` is the same guidance unlabelled, for output that carries the key
    in a column of its own.
    """

    def __init__(
        self, var_name: str, ref: str, message: str, reason: str | None = None
    ) -> None:
        self.var_name = var_name
        self.ref = ref
        self.message = message
        self.reason = reason if reason is not None else message
        super().__init__(message)
