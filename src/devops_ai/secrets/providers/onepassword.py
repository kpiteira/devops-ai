"""1Password items: `op://<vault>/<item>/<field>`, read through the `op` CLI.

The CLI carries the user's own grant; the provider adds nothing to it beyond the
process environment it is given, so `OP_ACCOUNT` and a service-account token
reach `op` exactly as they would from a shell.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "op://"
TIMEOUT = 30


def handles(ref: str) -> bool:
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Read the item through `op`, translating its failures into guidance."""
    # The child is spawned with `env=ctx.env`, and exec resolves the program on
    # *that* environment's PATH — including its fallback when the variable is
    # absent. Resolve here on the same PATH and hand the child the absolute
    # path, so there is no second search that could disagree with this one.
    executable = shutil.which("op", path=ctx.env.get("PATH", os.defpath))
    if executable is None:
        raise ProviderError(
            "1Password CLI (op) not found. "
            "Install: brew install 1password-cli "
            "— or use $VAR references instead."
        )

    try:
        result = subprocess.run(
            [executable, "read", "--no-newline", ref],
            capture_output=True,
            text=True,
            # The operator's locale is not the secret's encoding: under C, a
            # non-ASCII value would raise UnicodeDecodeError before it could be
            # returned. Matches the CLI's UTF-8 output path.
            encoding="utf-8",
            timeout=TIMEOUT,
            env=dict(ctx.env),
        )
    except subprocess.TimeoutExpired:
        raise ProviderError(
            "1Password CLI timed out. Try: eval $(op signin)"
        ) from None

    if result.returncode != 0:
        stderr = (result.stderr or "").lower()
        if "sign" in stderr or "auth" in stderr:
            raise ProviderError(
                "1Password not authenticated. Run: eval $(op signin)"
            )
        raise ProviderError(
            f"Secret not found in 1Password: {ref}. "
            f"Check the reference in infra.toml."
        )

    return str(result.stdout)
