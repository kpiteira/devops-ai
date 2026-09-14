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
import tempfile
from pathlib import Path

from .. import envfile
from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "dotenv://"
KEY_SEPARATOR = "#"
NEW_FILE_MODE = 0o600
NUL = "\0"
# A value that could not possibly be mistaken for part of a key, used to ask
# `envfile` whether a *key* survives a round trip independently of the value
# that follows it.
PROBE = "probe"


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
    # POSIX allows a line break in a filename, so this is reachable rather than
    # theoretical — and a write answers with the reference it was given, which
    # `ksecret write` prints. A reference carrying one would make stdout two
    # lines where the surface promises exactly one, the canonical reference,
    # and a caller reading that back stores half a reference.
    #
    # The one-line promise is enforced for every provider in `writer.write`,
    # which is the module that makes it; this repeats it because `dotenv.write`
    # is also called directly, and because the refusal has to come before any
    # file is touched. `azurekeyvault` keeps its own for a sharper reason still
    # — a line break there forges the error fields it parses back out of `az`.
    #
    # Here rather than in `_parse`, which reads share: M1-M3 read behaviour is
    # unchanged, and a read that already resolves such a file must keep doing
    # so. Only the write, which is new, refuses.
    if NUL in ref or ref.splitlines() != [ref]:
        raise ProviderError(
            f"Malformed reference {_visible(ref)}. A reference cannot contain "
            f"a NUL byte or a line break."
        )
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


def _visible(ref: str) -> str:
    """The reference with only its unprintable characters escaped.

    A reference nobody vetted is about to be named in a message a human reads,
    and echoing a raw line break hides the very thing the message is about.
    """
    return "".join(
        character if character.isprintable() else repr(character)[1:-1]
        for character in ref
    )


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
        # The line's own `export ` and indentation, not just its ending: a
        # `.env` that is `source`d stops exporting the variable if the word is
        # dropped, which is a change to what the file *does* — well outside
        # "set this key".
        kept.append(envfile.prefix(raw) + line + _ending(raw))
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
    if envfile.entry(f"{key}={PROBE}") != (key, PROBE):
        # The key, not the value: a name with an `=` in it, or with spaces
        # around it, or one that starts a comment, is read back as a different
        # key or as no key at all. Said separately because the sentence below
        # would blame the value for a reference's problem, and send someone
        # looking at the wrong half of what they typed.
        raise ProviderError(
            f"{key} cannot be a key in {path}: a {SCHEME} file reads a line as "
            f"`KEY=value`, so a name carrying an `=`, surrounding whitespace, "
            f"an `export ` prefix, or a leading `#` names something else once "
            f"it is written down."
        )
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
    a compose run or a colleague reads next. Flushed to the disk before the
    rename, so a machine that loses power right after this returns finds the
    new contents rather than an empty file under the old name.

    Beside the target rather than in the system temp directory, because
    `os.replace` is only atomic within a filesystem. The cost is the residual:
    a process killed between the write and the rename leaves one `.ksecret-*`
    file there, 0600 and holding the value. Atomicity is worth more than that.

    One writer at a time is assumed. Each write is a read-modify-write of the
    whole file, so two racing calls do not corrupt it — `os.replace` sees to
    that — but the later one wins outright and the earlier key is simply gone.

    A file that was already there keeps its own permissions — the user chose
    them, and a write to one key is not the moment to overrule that. A file we
    create is owner-only, said here rather than left to `mkstemp`'s default,
    because it is a promise this command makes and not an implementation note.

    The user's mode is restored *after* the rename, never copied onto the
    temporary file before it. The temporary already holds the value, so
    widening it first would publish the secret at the target's mode — 0644,
    say — for the window before the rename, under a name nobody is watching.
    Restoring afterwards inverts that window to owner-only, which is the
    direction that cannot hurt.
    """
    try:
        previous_mode = (path.stat().st_mode & 0o777) if existed else None
    except OSError:
        # It was there a moment ago. Falling back to owner-only keeps the
        # value unreadable rather than guessing a mode nobody stated.
        previous_mode = None
    try:
        handle, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=".ksecret-", suffix=".tmp"
        )
    except OSError as exc:
        raise ProviderError(f"Cannot write {path}: {exc.strerror}.") from None
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, NEW_FILE_MODE)
        os.replace(temporary, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise ProviderError(f"Cannot write {path}: {exc.strerror}.") from None
    if previous_mode is not None:
        # Outside the block above, and suppressed, because `os.replace` has
        # returned: the value *is* the file now. On a mount where rename works
        # and chmod does not — SMB, FAT, some FUSE — raising here would report
        # `Cannot write` over a write that succeeded, and a caller would abort
        # or retry a secret already stored. The mode is the part that may be
        # dropped; what is left is owner-only, the strict end of the mistake.
        with contextlib.suppress(OSError):
            os.chmod(path, previous_mode)
