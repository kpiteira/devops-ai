"""Azure Key Vault secrets: `akv://<vault>/<secret>`, read through the `az` CLI.

A bare reference reads the secret's current version; `akv://<vault>/<secret>/<version>`
reads that one. Auth is whatever `az login` established — a developer session, a
managed identity, a service principal — so the provider adds no credential handling
of its own, exactly as the 1Password provider adds nothing to an `op` grant.

Azure CLI failures are classified from stderr, not from exit status: `az keyvault
secret show` exits 3 for a missing secret and 1 for an unreachable vault, and neither
code is documented API. The Azure error codes that az prints on its `ERROR:` lines —
`SecretNotFound`, `Forbidden`, `SecretDisabled` — are, so those are the anchors, and
az's surrounding prose is only the fallback for states no code tells apart.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "akv://"
TIMEOUT = 30


def handles(ref: str) -> bool:
    """Claim the scheme even when nothing follows it, so a typo is a malformed
    reference rather than a literal that quietly resolves to itself."""
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Read the secret through `az`, translating its failures into guidance."""
    vault, secret, version = _parse(ref)

    # The child is spawned with `env=ctx.env`, and exec resolves the program on
    # *that* environment's PATH — including its fallback when the variable is
    # absent. Resolve here on the same PATH and hand the child the absolute
    # path, so there is no second search that could disagree with this one.
    executable = shutil.which("az", path=ctx.env.get("PATH", os.defpath))
    if executable is None:
        raise ProviderError(
            "Azure CLI (az) not found. "
            "Install: brew install azure-cli "
            "— or use $VAR references instead."
        )

    command = [
        executable, "keyvault", "secret", "show",
        "--vault-name", vault,
        "--name", secret,
        # JSON, not TSV: a value that ends in a newline or contains a tab comes
        # back byte-identical through `json.loads`, where TSV's row terminator
        # would be indistinguishable from the value's own trailing newline.
        "--query", "value", "--output", "json",
        # Keep stderr to az's own ERROR: lines, so classification reads signal.
        "--only-show-errors",
    ]
    if version is not None:
        command += ["--version", version]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            # The operator's locale is not the secret's encoding: under C, a
            # non-ASCII value would raise UnicodeDecodeError before it could be
            # returned.
            encoding="utf-8",
            timeout=TIMEOUT,
            env=dict(ctx.env),
        )
    except subprocess.TimeoutExpired:
        raise ProviderError(
            f"Azure CLI timed out reading {ref} after {TIMEOUT}s. "
            f"Check your network and that `az account show` succeeds."
        ) from None

    if result.returncode != 0:
        raise ProviderError(
            _diagnose(
                ref, vault, secret, version, result.returncode, result.stderr or ""
            )
        )

    return _value(ref, result.stdout)


def _parse(ref: str) -> tuple[str, str, str | None]:
    """Split a reference into vault, secret and optional version."""
    parts = ref[len(SCHEME):].split("/")
    if len(parts) not in (2, 3) or not all(parts):
        raise ProviderError(
            f"Malformed reference {ref}. Expected "
            f"{SCHEME}<vault>/<secret> or {SCHEME}<vault>/<secret>/<version>."
        )
    vault, secret = parts[0], parts[1]
    return vault, secret, parts[2] if len(parts) == 3 else None


def _value(ref: str, stdout: str) -> str:
    """The secret from az's JSON output, or a failure that never quotes it."""
    try:
        value = json.loads(stdout)
    except ValueError:
        raise ProviderError(
            f"Azure CLI returned output that is not JSON for {ref}."
        ) from None
    if not isinstance(value, str):
        raise ProviderError(f"Secret {ref} has no value in Azure Key Vault.")
    return value


def _diagnose(
    ref: str,
    vault: str,
    secret: str,
    version: str | None,
    code: int,
    stderr: str,
) -> str:
    """Name what went wrong from az's own error text.

    Azure answers several unrelated states with `(Forbidden)` — a missing role, a
    vault firewall, and a *disabled* secret all land there (verified 2026-09-12
    against the acceptance vault). Sending someone to chase RBAC for a secret they
    disabled themselves is a confident wrong answer, so the states that can be told
    apart are, and the rest carry az's own words rather than a guess.

    Only az's `ERROR:` lines are ever quoted back: a retrieval that failed holds no
    value to leak, but the invariant is absolute, so nothing else from the child
    reaches the message.
    """
    lowered = stderr.lower()
    if _names_code(lowered, "SecretNotFound") or (
        "was not found in this key vault" in lowered
    ):
        return f"Secret not found in Azure Key Vault: {ref}."
    # `az login` names itself in az's own guidance; matching the broader "please
    # run" would swallow unrelated advice such as `az account set`.
    if "az login" in lowered:
        return f"Azure CLI is not logged in, so {ref} cannot be read. Run: az login"
    if _names_code(lowered, "SecretDisabled") or "disabled secret" in lowered:
        # Disabling is per version: an older enabled version still reads (verified).
        return (
            f"Secret {secret} is disabled in Key Vault {vault}. Enable it, or pin "
            f"an enabled version: {SCHEME}{vault}/{secret}/<version>."
        )
    if (
        _names_code(lowered, "Forbidden")
        or "not authorized" in lowered
        or "access denied" in lowered
    ):
        return (
            f"Access denied reading {ref}.{_az_errors(stderr)} If that is a "
            f"permissions problem, your Azure identity needs the Key Vault "
            f"Secrets User role on {vault}."
        )
    if "failed to resolve" in lowered or "name or service not known" in lowered:
        return (
            f"Key Vault {vault} could not be reached — check the vault name "
            f"in {ref}."
        )
    detail = _az_errors(stderr) or (
        f" az printed no ERROR: line; run: {_retry(vault, secret, version)}"
    )
    return f"Azure CLI failed reading {ref} (exit status {code}).{detail}"


def _retry(vault: str, secret: str, version: str | None) -> str:
    """The command to run by hand when az failed without saying why.

    It reproduces the *same* read, pinned version included: the current version
    can be healthy while the pinned one is missing or disabled, so a retry that
    silently drops `--version` succeeds and proves the wrong thing.

    `--output none` because the retry is for the error, never the value — az's
    default JSON response carries the secret, and guidance that puts one on the
    operator's screen, into shell history and into CI logs is the leak this
    module refuses everywhere else.
    """
    pinned = f" --version {version}" if version is not None else ""
    return (
        f"az keyvault secret show --vault-name {vault} "
        f"--name {secret}{pinned} --output none"
    )


def _names_code(lowered: str, code: str) -> bool:
    """True when az named this Azure error code — not merely printed the word.

    Vault and secret names are the caller's to choose and az echoes them into
    stderr verbatim (the host it could not resolve, the secret URL it refused),
    so scanning for a bare `forbidden` lets a vault legitimately named
    `forbidden` take the RBAC branch and bury the real diagnosis. Only the three
    shapes az actually prints a code in count, all captured from the vault:
    `(Forbidden)` in the headline, `Code: Forbidden` on its own line, and
    `"code": "SecretDisabled"` inside an inner-error blob.
    """
    code = code.lower()
    return (
        f"({code})" in lowered
        or f"code: {code}" in lowered
        or f'"code": "{code}"' in lowered
    )


def _az_errors(stderr: str) -> str:
    """az's own ERROR: lines, joined — empty when it printed none."""
    lines = [
        line.partition("ERROR:")[2].strip()
        for line in stderr.splitlines()
        if line.startswith("ERROR:")
    ]
    return (" " + " ".join(lines)) if lines else ""
