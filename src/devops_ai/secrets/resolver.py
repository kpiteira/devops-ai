"""Resolve secret references through whatever providers are installed.

The resolver knows the shape of a provider, never the name of one: it walks the
providers package, asks each module whether it handles a reference, and hands
the work over. A reference no provider claims is a literal — bare text and
connection strings keep working, and an unrecognised scheme is reported by
`ksecret check` rather than silently failing at resolution time.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol, cast

from . import providers
from .context import ResolveContext
from .errors import ProviderError, SecretResolutionError

OK = "ok"
LITERAL = "literal"
ERROR = "error"

# The attribute a provider sets to say its values are bytes the OS handed us
# rather than text a format invented, so `encode_env`'s `surrogateescape` is
# right for them and this module's check is not.
#
# Read off the provider rather than listed here, because listing it would make
# adding a provider touch the resolver — the one thing this package's
# architecture forbids. It is an opt-out, never an opt-in: a provider added
# tomorrow is checked because its author did nothing, and passing raw bytes
# through is the line someone has to choose to write.
INHERITS_OS_BYTES = "INHERITS_OS_BYTES"


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


def literals(entries: Mapping[str, str]) -> dict[str, str]:
    """The entries no provider claims — the ones that are values, not references.

    They are placed in the environment before anything is resolved, so a
    reference can name a variable declared beside it. `ksecret run` and kinfra's
    `[sandbox.secrets]` both depend on this: an `OP_ACCOUNT` line has to reach
    the `op` process that the next line's reference spawns.
    """
    return {key: value for key, value in entries.items() if provider_for(value) is None}


def layered_env(
    entries: Mapping[str, str], base: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The environment `entries` resolve in: literals laid over the process env.

    Every caller that resolves a *mapping* of entries goes through this —
    `ksecret run`, `ksecret check`, `ksecret check --infra` and kinfra's
    `[sandbox.secrets]`. They have to agree: `--infra` exists to report what
    kinfra will do, so a context it builds differently is a wrong answer about
    the one thing it is for.
    """
    env = dict(os.environ if base is None else base)
    env.update(literals(entries))
    return env


def context_for(
    entries: Mapping[str, str], base_dir: Path | None = None
) -> ResolveContext:
    """The context `entries` resolve in — the environment *and* its provenance.

    The two have to be built together. `layered_env` lays the declared literals
    over the inherited environment, and a provider then spawns a child with the
    result; which half a value came from decides how its bytes are chosen, and
    the merged mapping no longer records that. Every caller that resolves a
    mapping of entries goes through here, so the answer cannot drift between
    `ksecret run`, `ksecret check`, `--infra` and kinfra's provisioning.

    Only the *literals* are declared. A reference's own name is not: an entry
    whose value is a reference leaves whatever `env` already held under that
    name untouched until it resolves, so an entry named `PATH` would still be
    the inherited `PATH` here — and claiming it would re-spell the very
    variable `utf8_keys` exists to protect.
    """
    env = layered_env(entries)
    declared = frozenset(literals(entries))
    if base_dir is None:
        return ResolveContext(env=env, declared=declared)
    return ResolveContext(base_dir=base_dir, env=env, declared=declared)


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
        return _representable(provider.resolve(ref, context), ref, provider)
    except ProviderError as exc:
        raise SecretResolutionError(
            var_name=var_name,
            ref=ref,
            message=f"{var_name}: {exc}",
            reason=str(exc),
        ) from None


def _representable(value: str, ref: str, provider: Provider) -> str:
    """`value` unchanged, or a refusal — never something a child cannot receive.

    A `str` carries no provenance, so this is the last point that knows where a
    value came from. Downstream, `encode_env` encodes with `surrogateescape`:
    for an inherited value that is right, and for a surrogate standing for no
    byte it silently hands the child a *different secret* than the vault holds.

    Parsing a text format is what manufactures one — `json.loads` turns a
    `\\uD800` escape into a lone surrogate, and nothing says the next provider
    will use JSON to do it. So the rule is on what a provider *returns*, not on
    how it got there: every value goes through here, whatever the provider
    parsed and however it spelled the call.

    (That escape is doubled deliberately. Written singly it is not a mention of
    a surrogate but one — a docstring is a string literal, so Python builds the
    character, and on 3.14 the module then cannot be compiled at all.)
    """
    if getattr(provider, INHERITS_OS_BYTES, False):
        return value
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        # Never `from`, and nothing of `value` in the sentence: the exception
        # being replaced quotes the character it choked on and its position.
        raise ProviderError(
            f"{ref} resolved to a value that is not valid text: it contains an "
            f"unpaired surrogate, which has no UTF-8 encoding."
        ) from None
    return value


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
        return CheckResult(key=var_name, status=ERROR, reason=exc.reason)
    return CheckResult(key=var_name, status=OK)
