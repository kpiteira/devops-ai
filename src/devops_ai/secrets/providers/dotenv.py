"""A key in a `KEY=value` file: `dotenv://<path>#<KEY>`.

The path is relative to the context's base directory — the working directory for
`ksecret`, the main repository root for kinfra, where a project's gitignored
files actually live.

Writing puts a value back into that file. The format has no escapes, so not
every value can be spelled in it; rather than argue about which can, this module
asks `envfile` — the reader — whether a line it is about to write says what it
means, and refuses when no spelling does. A value that cannot be read back is
never written.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from pathlib import Path

from .. import envfile
from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "dotenv://"
KEY_SEPARATOR = "#"
NEW_FILE_MODE = 0o600


def handles(ref: str) -> bool:
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Return the key's value, naming the file and the key when it is missing."""
    relative, key = _parse(ref)
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


def write(
    ref: str, value: str, ctx: ResolveContext, if_absent: bool = False
) -> str:
    """Set the key in the file, leaving every other line exactly as it was."""
    relative, key = _parse(ref)
    path = _target(ctx.path(relative))

    try:
        # `newline=""`, so the file arrives with its own line endings rather
        # than with universal newlines' translation of them. `read_text` would
        # hand back every CRLF as an LF, and writing that out again rewrites
        # every line in the file to make one key's value fit — the opposite of
        # what this promises. The reader is unaffected either way: `entry`
        # strips a line before it parses it.
        with path.open(encoding="utf-8", newline="") as stream:
            original = stream.read()
        existed = True
    except FileNotFoundError:
        original, existed = "", False
    except UnicodeDecodeError:
        # `envfile.read` reports the same failure the same way; a file we cannot
        # read is one we must not rewrite, because every other line in it would
        # have to be re-encoded on a guess.
        raise ProviderError(f"Cannot read {path}: not valid UTF-8 text.") from None
    except OSError as exc:
        raise ProviderError(f"Cannot read {path}: {exc.strerror}.") from None

    if if_absent and key in envfile.parse(original):
        return ref

    _save(path, _with_key(original, key, value, path), existed)
    return ref


def _parse(ref: str) -> tuple[str, str]:
    """Split a reference into path and key, or say what it should have been."""
    relative, separator, key = ref[len(SCHEME):].partition(KEY_SEPARATOR)
    if not relative or not separator or not key:
        raise ProviderError(
            f"Malformed reference {ref}. Expected "
            f"{SCHEME}<path>{KEY_SEPARATOR}<KEY>."
        )
    return relative, key


def _target(path: Path) -> Path:
    """The file to rewrite, with any symlink followed to what it names.

    `_save` finishes with `os.replace`, which would otherwise put a regular file
    where the link was and leave the file it pointed at holding the old value —
    a `.env` symlinked to a shared secrets file is an ordinary arrangement, and
    silently detaching it is not a thing a write to one key should do.

    Read does not do this, and does not need to: it follows the link by opening
    it. The two therefore name different paths in their messages for the same
    reference, which is the honest answer in each case — read failed at the
    link, and write would have happened at its target.
    """
    return Path(os.path.realpath(path))


def _with_key(text: str, key: str, value: str, path: Path) -> str:
    """`text` with `key` set to `value` and nothing else touched.

    Line endings are carried over from the line being replaced, so a CRLF file
    stays one; a file that ended without a newline gains one only if a line is
    appended after it.
    """
    line = _spelling(key, value, path)
    kept: list[str] = []
    replaced = False
    for raw in text.splitlines(keepends=True):
        declared = envfile.entry(raw)
        if declared is None or declared[0] != key:
            kept.append(raw)
            continue
        if replaced:
            # A second line for the same key is dropped rather than left to sit
            # above or below the one that now holds the value: which of them a
            # reader believes is a property of the reader, and this file has
            # just been told what the key is.
            continue
        kept.append(line + _ending(raw))
        replaced = True

    if not replaced:
        if kept and _ending(kept[-1]) == "":
            kept[-1] += "\n"
        kept.append(line + "\n")

    written = "".join(kept)
    # The promise is about the file, not about the line: `_spelling` proved one
    # line reads back as this value, and this proves the file does. They differ
    # wherever a line's meaning depends on what is around it, which is the sort
    # of thing a format grows and a writer finds out about late.
    if envfile.parse(written).get(key) != value:
        raise ProviderError(_unwritable(key, path))
    return written


def _ending(line: str) -> str:
    """Whatever terminated this line — `\\n`, `\\r\\n`, or nothing at all."""
    body = line.splitlines()[0] if line else ""
    return line[len(body):]


def _spelling(key: str, value: str, path: Path) -> str:
    """A line that `envfile` reads back as exactly this key and value.

    Bare first, quoted second — because quoting is what buys back the leading
    and trailing whitespace the reader strips, and a value that needs neither
    should not acquire quotes it never had. Asking the reader which spelling
    works, rather than deciding here, is what keeps the two from drifting: the
    rule for `'` and `"` lives in one place and this reads it.
    """
    for candidate in (value, f'"{value}"'):
        line = f"{key}={candidate}"
        if envfile.entry(line) == (key, value):
            return line
    raise ProviderError(_unwritable(key, path))


def _unwritable(key: str, path: Path) -> str:
    """Why a value will not go into this file — without ever showing it."""
    return (
        f"The value cannot be stored as {key} in {path}: a {SCHEME} file holds "
        f"one line per key and has no escapes, so a value containing a line "
        f"break cannot be written to one. Use a vault-backed reference for it."
    )


def _save(path: Path, text: str, existed: bool) -> None:
    """Replace the file's contents atomically, 0600 when we are creating it.

    Written beside the target and moved onto it, so a failure midway leaves the
    old file intact rather than a truncated one: this file is what a sandbox,
    a compose run or a colleague reads next.

    A file that was already there keeps its own permissions — the user chose
    them, and a write to one key is not the moment to overrule that. A file we
    create is owner-only, said here rather than left to `mkstemp`'s default,
    because it is a promise this command makes and not an implementation note.
    """
    try:
        handle, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=".ksecret-", suffix=".tmp"
        )
    except OSError as exc:
        raise ProviderError(f"Cannot write {path}: {exc.strerror}.") from None
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(text.encode("utf-8"))
        if existed:
            shutil.copymode(path, temporary)
        else:
            os.chmod(temporary, NEW_FILE_MODE)
        os.replace(temporary, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise ProviderError(f"Cannot write {path}: {exc.strerror}.") from None
