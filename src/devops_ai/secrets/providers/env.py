"""The host environment, falling back to the project's `.env` file.

`env://NAME` and its shorthand `$NAME` read exported variable `NAME`. When the
variable is not exported, the `.env` file beside the project falls back in —
compose semantics, so the zero-configuration workflow needs no rewriting. An
exported value always wins over the file.
"""

from __future__ import annotations

from .. import envfile
from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "env://"
SHORTHAND = "$"
FALLBACK_FILE = ".env"
# This provider hands back what `os.environ` holds, and that is bytes the OS
# gave us: Python decoded them with `surrogateescape`, so a surrogate in
# U+DC80..U+DCFF stands for a real byte and has to reach the child as that byte.
# Every other provider returns text, and the resolver refuses a surrogate from
# one of those — it stands for nothing, and `encode_env` would quietly hand the
# child a different secret than the backend holds. Only this module can know
# which kind its values are, so only this module says so.
INHERITS_OS_BYTES = True


def handles(ref: str) -> bool:
    """True for both the scheme and the `$NAME` shorthand.

    The scheme is claimed even with nothing after it, so a typo is a malformed
    reference rather than a literal that quietly resolves to itself. The bare
    sigil is not: a lone `$` is far likelier to be text than a mistyped
    reference.
    """
    if ref.startswith(SCHEME):
        return True
    return ref.startswith(SHORTHAND) and len(ref) > 1


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Return the variable's value, or raise naming the variable that is missing."""
    name = ref[len(SCHEME):] if ref.startswith(SCHEME) else ref[len(SHORTHAND):]
    if not name:
        raise ProviderError(
            f"Malformed reference {ref}. Expected {SCHEME}<NAME>."
        )
    if name in ctx.env:
        return ctx.env[name]

    fallback = ctx.path(FALLBACK_FILE)
    if not fallback.is_file():
        raise ProviderError(
            f"Environment variable {name} not set, and there is no {fallback} "
            f"to fall back to. Export it, or create that file."
        )
    try:
        values = envfile.read(fallback)
    except OSError as exc:
        raise ProviderError(
            f"Environment variable {name} not set, and {fallback} could not be "
            f"read: {exc.strerror}."
        ) from None
    if name not in values:
        raise ProviderError(
            f"Environment variable {name} not set, and no {name} entry in "
            f"{fallback}. Export it, or add it to that file."
        )
    return values[name]
