"""A key in a `KEY=value` file: `dotenv://<path>#<KEY>`.

The path is relative to the context's base directory — the working directory for
`ksecret`, the main repository root for kinfra, where a project's gitignored
files actually live.
"""

from __future__ import annotations

from .. import envfile
from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "dotenv://"
KEY_SEPARATOR = "#"


def handles(ref: str) -> bool:
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Return the key's value, naming the file and the key when it is missing."""
    body = ref[len(SCHEME):]
    relative, sep, key = body.partition(KEY_SEPARATOR)
    if not relative or not sep or not key:
        raise ProviderError(
            f"Malformed reference {ref}. Expected "
            f"{SCHEME}<path>{KEY_SEPARATOR}<KEY>."
        )

    path = ctx.path(relative)
    try:
        values = envfile.read(path)
    except FileNotFoundError:
        raise ProviderError(f"File not found: {path}.") from None
    except OSError as exc:
        raise ProviderError(f"Cannot read {path}: {exc.strerror}.") from None

    if key not in values:
        raise ProviderError(f"Key {key} not found in {path}.")
    return values[key]
