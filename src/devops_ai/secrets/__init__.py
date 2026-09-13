"""Secret references and the providers that resolve them.

`devops_ai.secrets` is the whole public surface: the CLI and kinfra import the
resolver from here and never a provider module.
"""

from __future__ import annotations

from .context import ResolveContext
from .envfile import parse as parse_env_file
from .envfile import read as read_env_file
from .environ import encode_env
from .errors import (
    EnvironmentEncodingError,
    ProviderError,
    SecretResolutionError,
)
from .resolver import (
    ERROR,
    LITERAL,
    OK,
    CheckResult,
    check,
    layered_env,
    literals,
    provider_for,
    resolve,
    resolve_all,
    schemes,
)

__all__ = [
    "ERROR",
    "LITERAL",
    "OK",
    "CheckResult",
    "EnvironmentEncodingError",
    "ProviderError",
    "ResolveContext",
    "SecretResolutionError",
    "check",
    "encode_env",
    "layered_env",
    "literals",
    "parse_env_file",
    "provider_for",
    "read_env_file",
    "resolve",
    "resolve_all",
    "schemes",
]
