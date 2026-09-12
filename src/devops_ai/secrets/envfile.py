"""The `KEY=value` file format shared by env files and reference files.

One format, three readers: the file a reference points into, the files
`ksecret run`/`check` take with `--env-file`, and the fallback file the host
environment provider consults. Comments and blank lines are ignored; `export `
prefixes and surrounding single or double quotes are stripped.
"""

from __future__ import annotations

from pathlib import Path

_EXPORT = "export "


def parse(text: str) -> dict[str, str]:
    """Parse env-file text into an ordered mapping. Malformed lines are ignored."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(_EXPORT):
            line = line[len(_EXPORT):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key:
            continue
        values[key] = _unquote(value.strip())
    return values


def read(path: Path) -> dict[str, str]:
    """Parse the env file at `path`. Raises OSError if it cannot be read."""
    return parse(path.read_text())


def _unquote(value: str) -> str:
    for quote in ('"', "'"):
        if len(value) >= 2 and value.startswith(quote) and value.endswith(quote):
            return value[1:-1]
    return value
