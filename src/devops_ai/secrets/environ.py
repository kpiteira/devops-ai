"""The bytes environment a child process is spawned with.

A POSIX environment is bytes; Python's is str. `subprocess` bridges the two
with `os.fsencode`, which encodes with the *filesystem* encoding — and that
follows the locale: ASCII under `LC_ALL=C`. So a resolved value holding one
accented character cannot be handed to a child at all there. The spawn raises
`UnicodeEncodeError` from inside CPython, and that exception quotes the
character it choked on — which, for a secret, is part of the secret.

Encoding here instead makes a resolved value reach the child as its own UTF-8
bytes whatever the parent's locale, and puts the one failure still possible
behind a sentence that names only the variable.

Only a *resolved* value, though. An inherited one is not ours to re-encode:
`PATH` is a list of directory names, and a directory whose on-disk name is the
byte `E9` is not found by a child told to look in `C3 A9`. Under a decodable
non-UTF-8 locale (`iso8859-15`, `cp1252`) those two differ, and encoding
everything alike turned `ksecret run -- <bare command>` into exit 127 — a
regression this file introduced and `utf8_keys` exists to undo. Inherited
values go back out through `os.fsencode`, the exact inverse of the decode that
produced them, so whatever the OS gave us is what the child receives.

Refusing to run under a non-UTF-8 locale was the alternative, and was
rejected: containers, cron and CI are exactly where `LC_ALL=C` is ordinary,
and a minimal image ships no `C.UTF-8` for PEP 538 coercion to find — so
refusing loudly would strand the environments this tool is written for.

POSIX only, as devops-ai already is (`fcntl` in `registry.py`): `subprocess`
accepts a bytes environment where `os.supports_bytes_environ` is true, and the
CPython docs give that as false on Windows.
"""

from __future__ import annotations

import os
from collections.abc import Collection, Mapping

from .errors import EnvironmentEncodingError

ENCODING = "utf-8"
# The handler `os.environ` was *decoded* with, so a lone surrogate in
# U+DC80..U+DCFF stands for a byte that was never UTF-8. Encoding with the same
# handler hands that byte back unchanged — which is what `$VAR` resolving to an
# undecodable inherited value needs, and why `resolver` lets `env://` alone.
ERRORS = "surrogateescape"


def encode_env(
    env: Mapping[str, str], utf8_keys: Collection[str] = ()
) -> dict[bytes, bytes]:
    """`env` as the bytes a child is spawned with.

    `utf8_keys` names the variables *we* put there — the resolved references and
    declared literals of an env file. Those carry the promise: the child gets
    their own UTF-8 bytes whatever the parent's locale.

    Every other variable was inherited, and is handed on exactly as the parent
    holds it (`os.fsencode`, the inverse of the decode that produced it). We did
    not author it and must not re-spell it; see the module docstring on `PATH`.

    `subprocess` puts a bytes mapping through `os.fsencode` unchanged, so this
    is the only place a child's environment encoding is chosen.
    """
    ours = frozenset(utf8_keys)
    encoded: dict[bytes, bytes] = {}
    for name, value in env.items():
        mine = name in ours
        key = _encode(name, "The variable name", name, mine)
        encoded[key] = _encode(value, "The value of", name, mine)
    return encoded


def _inherited(text: str, subject: str, name: str) -> bytes:
    """Back out the way it came in, whatever the locale's codec happens to be."""
    try:
        return os.fsencode(text)
    except UnicodeEncodeError:
        # Not reachable from `os.environ` itself, which decodes with
        # surrogateescape and so yields nothing this cannot re-encode. It *is*
        # reachable where a caller passes an environment carrying values it did
        # not declare to us: the `op://` and `akv://` providers hand `op` and
        # `az` a `ctx.env` holding declared literals, which came from a strict
        # UTF-8 decode and so can be real non-ASCII characters an ASCII locale
        # cannot spell. That failed before this module existed too — the
        # difference is that CPython raised from inside the spawn with the
        # offending character quoted, and this names the variable instead.
        raise EnvironmentEncodingError(
            f"{subject} {name} cannot be encoded back into the bytes it was "
            f"read as, so it cannot be passed to a child process."
        ) from None


def _encode(text: str, subject: str, name: str, mine: bool = True) -> bytes:
    if not mine:
        return _inherited(text, subject, name)
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
