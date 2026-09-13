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
    # The names in `env` that devops-ai put there, rather than inherited from
    # the process it runs in. A provider spawns a child with this environment,
    # and the two halves need different encoders: a declared value was read
    # from a file decoded as strict UTF-8 and is ours to spell, while an
    # inherited one must go back out as the bytes it came in as. `env` alone
    # cannot tell them apart, so a provider that guessed would be wrong in one
    # direction or the other — see `secrets.environ`. Empty is the safe
    # default: nothing claimed, so nothing re-spelled.
    declared: frozenset[str] = frozenset()

    def path(self, relative: str) -> Path:
        """Resolve a reference's path against the context's base directory."""
        path = Path(relative)
        return path if path.is_absolute() else self.base_dir / path
