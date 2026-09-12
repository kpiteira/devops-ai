"""Resolve secret references through whatever providers are installed.

The resolver knows the shape of a provider, never the name of one: it walks the
providers package, asks each module whether it handles a reference, and hands
the work over. A reference no provider claims is a literal — bare text and
connection strings keep working, and an unrecognised scheme is reported by
`ksecret check` rather than silently failing at resolution time.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, cast

from . import providers
from .context import ResolveContext
from .errors import ProviderError, SecretResolutionError

OK = "ok"
LITERAL = "literal"
ERROR = "error"


class Provider(Protocol):
    """What a provider module exports."""

    SCHEME: str

    def handles(self, ref: str) -> bool: ...

    def resolve(self, ref: str, ctx: ResolveContext) -> str: ...


@dataclass(frozen=True)
class CheckResult:
    """One reference's status, with no value attached."""

    key: str
    status: str
    reason: str | None = None

    def format(self) -> str:
        line = f"{self.key}: {self.status}"
        return f"{line} — {self.reason}" if self.reason else line


@lru_cache(maxsize=1)
def installed_providers() -> tuple[Provider, ...]:
    """Every provider module in the package, ordered by module name.

    Modules whose name starts with `_` are shared helpers, not providers.
    """
    found: list[Provider] = []
    for info in sorted(pkgutil.iter_modules(providers.__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{providers.__name__}.{info.name}")
        found.append(cast("Provider", module))
    return tuple(found)


def provider_for(ref: str) -> Provider | None:
    """The provider that claims `ref`, or None when it is a literal."""
    for provider in installed_providers():
        if provider.handles(ref):
            return provider
    return None


def schemes() -> list[str]:
    """Every scheme a provider claims — for documentation and diagnostics."""
    return sorted(provider.SCHEME for provider in installed_providers())


def resolve(
    var_name: str, ref: str, ctx: ResolveContext | None = None
) -> str:
    """Resolve one reference. Literals resolve to themselves.

    Raises SecretResolutionError labelled with `var_name`.
    """
    context = ctx if ctx is not None else ResolveContext()
    provider = provider_for(ref)
    if provider is None:
        return ref
    try:
        return provider.resolve(ref, context)
    except ProviderError as exc:
        raise SecretResolutionError(
            var_name=var_name, ref=ref, message=f"{var_name}: {exc}"
        ) from None


def resolve_all(
    refs: Mapping[str, str], ctx: ResolveContext | None = None
) -> tuple[dict[str, str], list[SecretResolutionError]]:
    """Resolve every reference, collecting all failures rather than stopping."""
    context = ctx if ctx is not None else ResolveContext()
    resolved: dict[str, str] = {}
    errors: list[SecretResolutionError] = []
    for var_name, ref in refs.items():
        try:
            resolved[var_name] = resolve(var_name, ref, context)
        except SecretResolutionError as exc:
            errors.append(exc)
    return resolved, errors


def check(
    var_name: str, ref: str, ctx: ResolveContext | None = None
) -> CheckResult:
    """Classify a reference without ever returning its value."""
    if provider_for(ref) is None:
        return CheckResult(key=var_name, status=LITERAL)
    try:
        resolve(var_name, ref, ctx)
    except SecretResolutionError as exc:
        return CheckResult(key=var_name, status=ERROR, reason=str(exc.message))
    return CheckResult(key=var_name, status=OK)
