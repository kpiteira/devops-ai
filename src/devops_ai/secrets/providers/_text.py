"""A resolved value is text that can reach a child, or it is refused here.

`json.loads` turns a `\\uD800` escape into a lone surrogate. Every other string
in this package came from a strict UTF-8 decode, so a surrogate cannot survive
one — but a JSON escape is not a decode, and both JSON-speaking providers
(`akv://`, `bao://`) can hand one back.

Nothing downstream can represent it. `secrets.encode_env` encodes with
`surrogateescape`, which would give the child a *raw byte* instead of the
value's UTF-8: a different secret than the vault holds, with nothing raised.
That handler is right where it is, because `env://` resolves to a value this
process inherited, whose surrogates do stand for real bytes. The two kinds are
indistinguishable by then — a `str` carries no provenance — so the refusal
belongs at the boundary that still knows which kind it has.

Underscore-prefixed: shared code inside the providers package, not a provider.
`tests/architecture/test_secret_providers.py` reads the prefix that way, and
`test_child_env_encoding.py` requires every `json.loads` provider to come
through here.
"""

from __future__ import annotations

from ..errors import ProviderError


def utf8_text(value: str, ref: str, source: str) -> str:
    """`value` unchanged, or a refusal that never quotes it.

    `source` names who returned it, so the sentence says where to go looking;
    `ref` is the reference, which carries no secret material.
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ProviderError(
            f"{source} returned a value for {ref} that is not valid text: it "
            f"contains an unpaired surrogate."
        ) from None
    return value
