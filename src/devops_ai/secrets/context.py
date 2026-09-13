"""The environment a reference is resolved in.

Two things vary between callers: where relative paths point, and which process
environment providers read and hand to the tools they shell out to.

- `ksecret` resolves against the working directory and the real environment.
- kinfra resolves against the main repository root (gitignored files live there,
  not in a worktree) and the environment of the `kinfra` process.
- `ksecret run` resolves against an environment that already carries the literal
  lines of its env files, so a reference can name a variable declared beside it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ResolveContext:
    """Where a reference resolves from."""

    base_dir: Path = field(default_factory=Path.cwd)
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)

    def path(self, relative: str) -> Path:
        """Resolve a reference's path against the context's base directory."""
        path = Path(relative)
        return path if path.is_absolute() else self.base_dir / path
