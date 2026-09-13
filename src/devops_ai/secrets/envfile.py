"""The `KEY=value` file format shared by env files and reference files.

One format, three readers and one writer: the file a reference points into,
the files `ksecret run`/`check` take with `--env-file`, the fallback file the
host environment provider consults, and `ksecret write`, which puts a value
back into the first of those. Comments and blank lines are ignored; `export `
prefixes and surrounding single or double quotes are stripped.
"""

from __future__ import annotations

import errno
from pathlib import Path

_EXPORT = "export "


def entry(line: str) -> tuple[str, str] | None:
    """The key and value one line declares, or None when it declares neither.

    The single place that decides what a line means. A writer has to agree with
    the reader about which line defines a key and about how a value spells
    itself, or it produces a file that reads back as something else — so it
    asks this function rather than reimplementing the rules beside it.
    """
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if text.startswith(_EXPORT):
        text = text[len(_EXPORT):].lstrip()
    key, sep, value = text.partition("=")
    if not sep:
        return None
    key = key.strip()
    if not key:
        return None
    return key, _unquote(value.strip())


def parse(text: str) -> dict[str, str]:
    """Parse env-file text into an ordered mapping. Malformed lines are ignored."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        declared = entry(raw)
        if declared is not None:
            values[declared[0]] = declared[1]
    return values


def read(path: Path) -> dict[str, str]:
    """Parse the env file at `path`. Raises OSError if it cannot be read.

    Undecodable bytes come back as an OSError too: every caller promises an
    actionable message for a file it cannot read, and a `UnicodeDecodeError`
    escaping to the top is a traceback instead of one.
    """
    try:
        return parse(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise OSError(
            errno.EILSEQ, "not valid UTF-8 text", str(path)
        ) from None


def _unquote(value: str) -> str:
    for quote in ('"', "'"):
        if len(value) >= 2 and value.startswith(quote) and value.endswith(quote):
            return value[1:-1]
    return value
