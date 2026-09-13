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
import re
import shlex
import shutil
import subprocess

from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "akv://"
TIMEOUT = 30
NUL = "\0"


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
    # A NUL cannot survive exec: `subprocess.run` raises ValueError before `az`
    # starts, and the resolver only translates ProviderError — so it would leave
    # `ksecret check`, whose whole job is to *report* what resolves, dumping a
    # traceback instead. Rejected here as the malformed reference it is. This is
    # not the deferred question of validating names against Azure's rules: it is
    # the one character that cannot reach a child process at all.
    if NUL in ref:
        shown = ref.replace(NUL, "\\0")
        raise ProviderError(
            f"Malformed reference {shown}. A reference cannot contain a NUL byte."
        )
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
    """Name what went wrong, reading az's error from the fields that carry it.

    Azure answers several unrelated states with `(Forbidden)` — a missing role, a
    vault firewall, and a *disabled* secret all land there (verified against the
    acceptance vault). Telling a missing role from a firewall matters, so the
    states that can be told apart are, and the rest carry az's own words rather
    than a guess. A disabled secret is the exception: it is answered as absent,
    on purpose, and never reaches the Forbidden branch.

    None of that may be read out of the raw response. `_parse` accepts any
    non-empty segment, so a secret named `(Forbidden)` reaches az — which answers
    `BadParameter` and echoes the rejected name back inside its message. A scan
    of the whole response then reports an invalid name as access denied, and a
    name carrying `does not allow operation '<version>'` steals the bad-version
    branch. Both were reproduced before this was written. So: a code counts only
    where az writes codes, and message text counts only at a message's start,
    which is the one position an echoed name can never occupy.
    """
    codes, messages = _az_error_fields(stderr)

    def coded(name: str) -> bool:
        return name.lower() in codes

    def message_starts(prefix: str) -> bool:
        return any(m.lower().startswith(prefix) for m in messages)

    # A disabled secret answers exactly as an absent one — same exit code, same
    # sentence, same reference (Karl, 2026-09-13). Whether a name exists in the
    # vault is not something a caller who cannot read it gets to learn, so the
    # two states are deliberately indistinguishable from outside. Both shapes
    # Azure reports it in are captured here, from the same verified response:
    # the inner-error code, and the Forbidden headline naming the state.
    disabled = coded("SecretDisabled") or (
        coded("Forbidden")
        and message_starts("operation get is not allowed on a disabled secret")
    )
    if coded("SecretNotFound") or disabled:
        return f"Secret not found in Azure Key Vault: {ref}."
    # az appends a pinned version to the request path, so Key Vault reads a
    # segment that is not a version id as an *operation* name and refuses it —
    # true, and useless to whoever wrote `/latest`. `list-versions` returns
    # identifiers and attributes only, never values, so it is safe to send an
    # operator there.
    if version is not None and coded("BadParameter") and _refused_operation(
        messages, version
    ):
        return (
            f"{version} is not a version id in {ref}. Omit it to read the "
            f"current version, or take an id from: "
            + _az_command("list-versions", "--vault-name", vault, "--name", secret)
        )
    # An ERROR: line with no code is az speaking for itself rather than relaying
    # a Key Vault response, which is exactly what "not logged in" is. Requiring
    # that keeps an echoed name — which always arrives *with* a code — out.
    if message_starts("please run 'az login'") or (
        not codes and any("az login" in m.lower() for m in messages)
    ):
        return f"Azure CLI is not logged in, so {ref} cannot be read. Run: az login"
    if coded("Forbidden"):
        # Second layer under `_az_errors`' phrase filter: this is the branch a
        # disabled secret would fall into if Azure ever reworded the response
        # past both anchors above, so any mention of the word at all suppresses
        # the relay here. It costs detail on a genuine denial for a secret
        # actually named `disabled` — cheap, next to disclosing the state — and
        # it cannot misroute, because the branch is still chosen by code.
        relayed = _az_errors(stderr)
        if "disabled" in relayed.lower():
            relayed = ""
        return (
            f"Access denied reading {ref}.{relayed} If that is a "
            f"permissions problem, your Azure identity needs the Key Vault "
            f"Secrets User role on {vault}."
        )
    if not codes and any(
        phrase in message.lower()
        for message in messages
        for phrase in ("failed to resolve", "name or service not known")
    ):
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
    pinned = ["--version", version] if version is not None else []
    return _az_command(
        "show", "--vault-name", vault, "--name", secret, *pinned,
        # The retry is for the error, never the value.
        "--output", "none",
    )


def _az_command(*args: str) -> str:
    """An `az` command line that is safe for an operator to paste into a shell.

    `_parse` accepts any non-empty segment, and a reference does not only come
    from the operator's own keyboard — a committed `[sandbox.secrets]` entry is
    one too. Interpolating those segments raw put `$(…)` into text this module
    explicitly tells a human to run, which is a command substitution waiting for
    a copy-paste. Quoting makes it an argument instead. Ordinary vault and secret
    names need no quotes, so the message a real failure produces is unchanged.
    """
    return shlex.join(["az", "keyvault", "secret", *args])


_ERROR_LINE = re.compile(r"^ERROR:\s*(?:\(([A-Za-z]+)\)\s*)?(.*)$")
_CODE_LINE = re.compile(r"^Code:\s*([A-Za-z]+)\s*$")
_INNER_CODE_LINE = re.compile(r'^\s*"code":\s*"([A-Za-z]+)"')
_OPERATION_REFUSAL = re.compile(
    r"^method\s+\w+\s+does not allow operation\s+'(.*)'\.?$"
)


def _az_error_fields(stderr: str) -> tuple[frozenset[str], tuple[str, ...]]:
    """The error codes az reported, and the message text of each `ERROR:` line.

    Every pattern is anchored to the start of a line, because that is the one
    place a vault or secret name cannot reach: az echoes rejected names inside
    message text, never as a line of their own. The three code positions are all
    captured from the acceptance vault — `ERROR: (Forbidden)` in the headline, a
    standalone `Code: Forbidden`, and `"code": "SecretDisabled"` in an inner
    error. Only the *first* parenthesised token of an `ERROR:` line is a code; a
    later one is prose.
    """
    codes: set[str] = set()
    messages: list[str] = []
    for line in stderr.splitlines():
        error = _ERROR_LINE.match(line)
        if error is not None:
            if error.group(1) is not None:
                codes.add(error.group(1).lower())
            messages.append(error.group(2))
            continue
        for pattern in (_CODE_LINE, _INNER_CODE_LINE):
            found = pattern.match(line)
            if found is not None:
                codes.add(found.group(1).lower())
                break
    return frozenset(codes), tuple(messages)


def _refused_operation(messages: tuple[str, ...], version: str) -> bool:
    """True when az's message *is* Key Vault refusing this version as an operation.

    Anchored at the message start and compared against the pinned version, so a
    secret name spelling the same sentence cannot claim the branch.
    """
    for message in messages:
        refusal = _OPERATION_REFUSAL.match(message.strip().lower())
        if refusal is not None and refusal.group(1) == version.lower():
            return True
    return False


def _az_errors(stderr: str) -> str:
    """az's own ERROR: lines, joined — empty when it printed none.

    A line naming a *disabled* secret is dropped rather than relayed. A disabled
    secret is reported as an absent one, and a path that could not classify the
    response would otherwise hand back az's words and disclose the very
    difference that decision exists to hide. Filtering here rather than at each
    caller means no present or future relay can leak it. The phrase carries a
    space, which no legal Key Vault name does, so an echoed name cannot forge
    it — and cannot suppress an unrelated diagnosis either.
    """
    lines = [
        line.partition("ERROR:")[2].strip()
        for line in stderr.splitlines()
        if line.startswith("ERROR:") and "disabled secret" not in line.lower()
    ]
    return (" " + " ".join(lines)) if lines else ""
