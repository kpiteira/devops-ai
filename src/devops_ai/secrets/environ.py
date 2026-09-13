"""The bytes environment a child process is spawned with.

A POSIX environment is bytes; Python's is str. `subprocess` bridges the two
with `os.fsencode`, which encodes with the *filesystem* encoding — and that
follows the locale: ASCII under `LC_ALL=C`. So a resolved value holding one
accented character cannot be handed to a child at all there. The spawn raises
`UnicodeEncodeError` from inside CPython, and that exception quotes the
character it choked on — which, for a secret, is part of the secret.

Encoding here instead makes the child's environment the resolved values' own
UTF-8 bytes whatever the parent's locale, and puts the one failure still
possible behind a sentence that names only the variable.

Refusing to run under a non-UTF-8 locale was the alternative, and was
rejected: containers, cron and CI are exactly where `LC_ALL=C` is ordinary,
and a minimal image ships no `C.UTF-8` for PEP 538 coercion to find — so
refusing loudly would strand the environments this tool is written for.

POSIX only, as devops-ai already is (`fcntl` in `registry.py`): `subprocess`
accepts a bytes environment where `os.supports_bytes_environ` is true, and the
CPython docs give that as false on Windows.
"""

from __future__ import annotations

from collections.abc import Mapping

from .errors import EnvironmentEncodingError

ENCODING = "utf-8"
# The handler `os.environ` was *decoded* with, so a lone surrogate in
# U+DC80..U+DCFF stands for a byte that was never UTF-8. Encoding with the same
# handler hands that byte back unchanged. "strict" would refuse it instead, and
# the variable carrying it is typically one this process merely inherited.
#
# Deliberately the same handler for a *resolved* value, which looks wrong and
# is not. By here a `str` carries no provenance, so this cannot tell an
# inherited byte from a surrogate a text format invented — and it does not have
# to: `resolver._representable` has already refused the second kind for every
# provider but `env://`, whose values are inherited bytes by definition. What
# reaches this line is therefore only ever the kind `surrogateescape` is for.
ERRORS = "surrogateescape"


def encode_env(env: Mapping[str, str]) -> dict[bytes, bytes]:
    """`env` as the bytes a child is spawned with, UTF-8 whatever the locale.

    `subprocess` puts a bytes mapping through `os.fsencode` unchanged, so this
    is the only place a child's environment encoding is chosen.
    """
    encoded: dict[bytes, bytes] = {}
    for name, value in env.items():
        key = _encode(name, "The variable name", name)
        encoded[key] = _encode(value, "The value of", name)
    return encoded


def _encode(text: str, subject: str, name: str) -> bytes:
    try:
        return text.encode(ENCODING, ERRORS)
    except UnicodeEncodeError:
        # `from None`, and nothing of `text` in the sentence: the exception
        # being replaced carries the offending character and its position, and
        # a chained one would print under it. After surrogateescape the only
        # input left that cannot encode is a surrogate outside DC80..DCFF.
        raise EnvironmentEncodingError(
            f"{subject} {name} cannot be encoded as {ENCODING} for a child "
            f"process environment: it contains an unpaired surrogate."
        ) from None
