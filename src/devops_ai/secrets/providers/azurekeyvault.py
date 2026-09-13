"""Azure Key Vault secrets: `akv://<vault>/<secret>`, read through the `az` CLI.

A bare reference reads the secret's current version; `akv://<vault>/<secret>/<version>`
reads that one. Vault, secret and version are each checked against the shape Key
Vault requires before anything is spawned, so a reference it could never accept is
refused here by name instead of arriving as an echo inside az's error text
(issue #60). Auth is whatever `az login` established — a developer session, a
managed identity, a service principal — so the provider adds no credential handling
of its own, exactly as the 1Password provider adds nothing to an `op` grant.

Writing stores a new version of the secret. The value goes to `az` in a file only
this user can open, never in an argument, because `--value` would put it in the
process table — the whole reason `az` grew `--file`. The file is removed as soon
as `az` has exited, whether it succeeded or not.

Azure CLI failures are classified from stderr, not from exit status: `az keyvault
secret show` exits 3 for a missing secret and 1 for an unreachable vault, and neither
code is documented API. The Azure error codes that az prints on its `ERROR:` lines —
`SecretNotFound`, `Forbidden`, `SecretDisabled` — are, so those are the anchors, and
az's surrounding prose is only the fallback for states no code tells apart.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Iterator

from ..context import ResolveContext
from ..environ import encode_env
from ..errors import EnvironmentEncodingError, ProviderError

SCHEME = "akv://"
TIMEOUT = 30
NUL = "\0"
CR = "\r"
# Owner-only, and said rather than inherited from `mkstemp`: the value spends a
# moment on disk so that it never spends one in argv, and which of the two is
# the smaller exposure depends entirely on this number.
VALUE_FILE_MODE = 0o600

# The rules a reference's segments must satisfy before anything is spawned.
# Each is deliberately *more* permissive than Key Vault — which additionally
# constrains where a vault name's hyphens may sit and how long a secret name may
# be — so that this refuses only what Azure certainly refuses. az still answers
# for the rest, and now only for names it could have accepted.
#
# `\Z`, not `$`: `$` also matches before a final newline, so `^...{3,24}$` accepts
# `my-vault\n`. That is unreachable today, since the line-break guard above runs
# first — but a newline in a segment is the whole reason these rules exist, and a
# rule that admits one is not a rule, whatever currently stands in front of it.
_VAULT_NAME = re.compile(r"^[a-zA-Z0-9-]{3,24}\Z")
_SECRET_NAME = re.compile(r"^[0-9a-zA-Z-]+\Z")
# Key Vault writes version ids in lower case (measured: twelve ids in the
# acceptance vault, all 32 lower-case hex). Upper case is accepted anyway, rather
# than refuse an id that survived a round trip through something that recased it.
_VERSION_ID = re.compile(r"^[0-9a-fA-F]{32}\Z")


def handles(ref: str) -> bool:
    """Claim the scheme even when nothing follows it, so a typo is a malformed
    reference rather than a literal that quietly resolves to itself."""
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Read the secret through `az`, translating its failures into guidance."""
    vault, secret, version = _parse(ref)
    executable = _executable(ctx)

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
            env=encode_env(ctx.env, utf8_keys=ctx.declared),
        )
    except EnvironmentEncodingError as exc:
        raise ProviderError(str(exc)) from None
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


def write(ref: str, value: str, ctx: ResolveContext) -> str:
    """Store a new version of the secret, handing `az` the value in a file."""
    vault, secret, version = _parse(ref)
    if version is not None:
        raise ProviderError(
            f"{_visible(ref)} pins a version, and a version is an address to "
            f"read, not one to write: Key Vault mints the id for whatever is "
            f"stored. Drop the version to store a new one of {secret}."
        )
    if CR in value:
        # Measured against a live vault: `az` reads the `--file` it is given as
        # *text*, so universal newlines turn CR and CRLF into LF before Key
        # Vault ever sees them. The secret would then read back as something
        # other than what was written, which is the one thing a write promises
        # not to do — and failing loudly beats storing a near-miss credential
        # nobody will think to compare.
        raise ProviderError(
            f"{_visible(ref)} was not written: the value contains a carriage "
            f"return, and the Azure CLI rewrites CR and CRLF to LF in the file "
            f"it reads, so the secret would not read back as what was written. "
            f"Store it with LF line endings, or encode it (base64, say)."
        )
    executable = _executable(ctx)

    with _value_file(value) as path:
        command = [
            executable, "keyvault", "secret", "set",
            "--vault-name", vault,
            "--name", secret,
            # `--file`, never `--value`: an argument is readable by every other
            # process on the machine for as long as `az` runs.
            "--file", path,
            # Nothing on stdout: az's default response for `set` is the secret
            # object, value included, and this command prints only a reference.
            "--output", "none",
            # Keep stderr to az's own ERROR: lines, so classification reads
            # signal.
            "--only-show-errors",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=TIMEOUT,
                env=encode_env(ctx.env, utf8_keys=ctx.declared),
            )
        except EnvironmentEncodingError as exc:
            raise ProviderError(str(exc)) from None
        except subprocess.TimeoutExpired:
            raise ProviderError(
                f"Azure CLI timed out writing {ref} after {TIMEOUT}s. It may or "
                f"may not have stored the value; check with `az keyvault secret "
                f"show` before writing again. Check your network and that "
                f"`az account show` succeeds."
            ) from None

    if result.returncode != 0:
        raise ProviderError(
            _diagnose(
                ref, vault, secret, None, result.returncode, result.stderr or "",
                writing=True,
            )
        )
    return ref


def _executable(ctx: ResolveContext) -> str:
    """The `az` to run, found on the PATH the child will be given.

    The child is spawned with `env=ctx.env`, and exec resolves the program on
    *that* environment's PATH — including its fallback when the variable is
    absent. Resolving here on the same PATH and handing the child the absolute
    path means there is no second search that could disagree with this one.
    """
    executable = shutil.which("az", path=ctx.env.get("PATH", os.defpath))
    if executable is None:
        raise ProviderError(
            "Azure CLI (az) not found. "
            "Install: brew install azure-cli "
            "— or use $VAR references instead."
        )
    return executable


@contextlib.contextmanager
def _value_file(value: str) -> Iterator[str]:
    """The value in a file only its owner can read, gone when the block ends.

    `mkstemp` opens with 0600 already; the mode is set again because it is the
    property that makes this an acceptable place for a secret, and a promise
    worth stating where someone reading the call can see it. The removal is in
    a `finally` so a failing `az`, a timeout and an interpreter error all leave
    the same nothing behind.
    """
    handle, path = tempfile.mkstemp(prefix="ksecret-", suffix=".value")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(value.encode("utf-8"))
        os.chmod(path, VALUE_FILE_MODE)
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


def _parse(ref: str) -> tuple[str, str, str | None]:
    """Split a reference into vault, secret and optional version."""
    # Two character classes never belong in a reference, for different reasons.
    #
    # A NUL cannot survive exec: `subprocess.run` raises ValueError before `az`
    # starts, and the resolver translates only ProviderError, so it would leave
    # `ksecret check` — whose whole job is to *report* what resolves — dumping a
    # traceback.
    #
    # A line break is worse than cosmetic: az echoes a rejected name back, so a
    # segment carrying one splits into a line of its own in az's output, and a
    # name like `x<LF>Code: Forbidden` forges the very field `_az_error_fields`
    # reads codes from. Line-anchoring cannot help — the forged line *is* a
    # line. Verified: `\r`, `\v`, `\x1c`, `\x85` and `\u2028` all do it, not
    # just `\n`, so the test is `str.splitlines()` itself rather than a list of
    # characters to keep in step with it.
    #
    # They are checked ahead of the name rules below because the generic
    # malformed-reference message names the whole reference, and a reference
    # that never splits into segments would reach it carrying them.
    if NUL in ref or ref.splitlines() != [ref]:
        raise ProviderError(
            f"Malformed reference {_visible(ref)}. A reference cannot contain a "
            f"NUL byte or a line break."
        )
    parts = ref[len(SCHEME):].split("/")
    if len(parts) not in (2, 3) or not all(parts):
        raise ProviderError(
            f"Malformed reference {_visible(ref)}. Expected "
            f"{SCHEME}<vault>/<secret> or {SCHEME}<vault>/<secret>/<version>."
        )
    vault, secret = parts[0], parts[1]
    version = parts[2] if len(parts) == 3 else None

    # Segments Azure itself would reject are refused here rather than sent, in
    # the order they appear, so a reference wrong in two places names the first.
    if _VAULT_NAME.match(vault) is None:
        raise ProviderError(
            f"{_visible(vault)} is not a Key Vault name in {_visible(ref)}. "
            f"A vault name is 3 to 24 characters of letters, digits and hyphens."
        )
    if _SECRET_NAME.match(secret) is None:
        raise ProviderError(
            f"{_visible(secret)} is not a Key Vault secret name in "
            f"{_visible(ref)}. A secret name is letters, digits and hyphens "
            f"only — no underscores, spaces, dots or accents."
        )
    if version is not None and _VERSION_ID.match(version) is None:
        # The guidance az's own refusal used to earn, now given without the
        # call: Key Vault reads a non-id segment as an operation name, so its
        # answer never mentions versions at all and cost a round-trip to get.
        # `list-versions` returns identifiers and attributes only, never values,
        # so it is safe to send an operator there.
        raise ProviderError(
            f"{_visible(version)} is not a version id in {_visible(ref)} — a "
            f"version id is 32 hexadecimal characters. Omit it to read the "
            f"current version, or take an id from: "
            + _az_command("list-versions", "--vault-name", vault, "--name", secret)
        )
    return vault, secret, version


def _visible(ref: str) -> str:
    """The reference with only its unprintable characters escaped.

    Echoing a raw line break or NUL into a terminal hides the very thing the
    message is about, and an ANSI escape is worse than hidden: the terminal acts
    on it. A refused segment is named in a message a human reads, and a refused
    segment is by definition one nobody vetted, so the whole unprintable class is
    escaped rather than the two characters that happened to be found first.

    Everything printable is left alone — `str.isprintable()` counts an accent as
    printable and a space as printable — so a name a human can read stays one.
    """
    return "".join(
        char if char.isprintable() else char.encode("unicode_escape").decode("ascii")
        for char in ref
    )


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
    # `json.loads` can manufacture a lone surrogate from a `\uD800` escape,
    # which no encoding can represent. Refused for every provider at once by
    # `resolver._representable`, so this one need not know about it.
    return value


def _diagnose(
    ref: str,
    vault: str,
    secret: str,
    version: str | None,
    code: int,
    stderr: str,
    writing: bool = False,
) -> str:
    """Name what went wrong, reading az's error from the fields that carry it.

    Azure answers several unrelated states with `(Forbidden)` — a missing role, a
    vault firewall, and a *disabled* secret all land there (verified against the
    acceptance vault). Telling a missing role from a firewall matters, so the
    states that can be told apart are, and the rest carry az's own words rather
    than a guess. A disabled secret is the exception: it is answered as absent,
    on purpose, and never reaches the Forbidden branch.

    None of that may be read out of the raw response. az echoes a rejected name
    back inside its message, so a scan of the whole response reported an invalid
    name as access denied, and a name carrying `does not allow operation
    '<version>'` stole the bad-version branch. Both were reproduced before this
    was written. So: a code counts only where az writes codes, and message text
    counts only at a message's start, which is the one position an echoed name
    can never occupy.

    `_parse` now refuses the names that made those echoes reachable, which is
    where that class of defect is actually closed (issue #60). This anchoring
    stays as the second line: it is what holds if Azure ever echoes something
    else, and it costs nothing to keep.

    `writing` changes the verb and, more than cosmetically, the role: Key Vault
    Secrets *User* is a read-only role, so offering it to someone whose write
    was denied is advice that cannot work. The branches themselves are shared
    because the parsing they rest on was the hard part, and a second copy of it
    would be a second thing to get wrong when Azure rewords something.
    """
    codes, messages = _az_error_fields(stderr)
    attempted = "written" if writing else "read"

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
    if coded("Conflict") and message_starts("secret "):
        # A deleted secret's name is not free until the deletion finishes, and
        # on a vault with purge protection not until it is recovered or purged.
        # Verified against the acceptance vault, which answers `(Conflict)` with
        # an `ObjectIsBeingDeleted` inner code. Relayed whole: the message names
        # only the secret the caller asked for, and the remedy is in it.
        return (
            f"{ref} was not written.{_az_errors(stderr)} Recover it with "
            f"`az keyvault secret recover`, purge it, or use another name."
        )
    # A branch reading Key Vault's "does not allow operation '<segment>'" reply
    # used to sit here: az appends a pinned version to the request path, so a
    # segment that is not a version id arrives as an *operation* name. `_parse`
    # refuses those segments without a call now, so the reply cannot arrive and
    # the guidance it built is issued there instead. Keeping both would leave one
    # sentence written in two places, only one of which can ever run.
    # Anchored at the start of the message, which is the one position an echoed
    # name cannot occupy: az names the rejected input at the *end* of an
    # invalid-name message and inside a URL elsewhere. A looser scan here read a
    # vault legitimately reachable-sounding — `akv://az login/s` — as a login
    # prompt, because its DNS failure echoes the name and carries no code, so
    # "an echo always arrives with a code" was simply wrong for that path.
    #
    # An `az login` message that does not start this way (a token-expiry
    # AADSTS…, say) now falls through to the generic branch, which relays az's
    # own words — so the advice still reaches the reader, just untailored.
    if message_starts("please run 'az login'"):
        return (
            f"Azure CLI is not logged in, so {ref} cannot be {attempted}. "
            f"Run: az login"
        )
    if coded("Forbidden"):
        # This is the branch a disabled secret falls into if Azure ever rewords
        # the response past both anchors above, so a mention of the state
        # suppresses the relay here. It costs detail on a genuine denial for a
        # secret actually named `disabled` — cheap, next to disclosing the
        # state — and cannot misroute, because the branch is chosen by code.
        role = "Secrets Officer" if writing else "Secrets User"
        return (
            f"Access denied {'writing' if writing else 'reading'} {ref}."
            f"{_az_errors(stderr, hide_state=True)} If that is a "
            f"permissions problem, your Azure identity needs the Key Vault "
            f"{role} role on {vault}."
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
    # An invalid-request response echoes back only what the caller typed, so
    # relaying it discloses nothing about the vault — the caller already knows
    # what they wrote. Anything unclassified might be Azure describing state, so
    # there the mention is dropped. Getting this backwards discarded az's real
    # reason for a name like `disabled secret` *and* claimed az had printed no
    # ERROR: line, which was simply false.
    detail = _az_errors(stderr, hide_state=not coded("BadParameter")) or (
        f" az printed no ERROR: line; run: "
        f"{_retry(vault, secret, version, writing)}"
    )
    verb = "writing" if writing else "reading"
    return f"Azure CLI failed {verb} {ref} (exit status {code}).{detail}"


def _retry(vault: str, secret: str, version: str | None, writing: bool = False) -> str:
    """The command to run by hand when az failed without saying why.

    It reproduces the *same* call, pinned version included: the current version
    can be healthy while the pinned one is missing or disabled, so a retry that
    silently drops `--version` succeeds and proves the wrong thing.

    `--output none` because the retry is for the error, never the value — az's
    default JSON response carries the secret, and guidance that puts one on the
    operator's screen, into shell history and into CI logs is the leak this
    module refuses everywhere else. For a write the same rule picks `--file`
    over `--value`, with the path left as a placeholder: a command line that a
    reader completes with a filename cannot be one they complete with a secret.
    """
    if writing:
        return _az_command(
            "set", "--vault-name", vault, "--name", secret,
            "--file", "<file holding the value>", "--output", "none",
        )
    pinned = ["--version", version] if version is not None else []
    return _az_command(
        "show", "--vault-name", vault, "--name", secret, *pinned,
        # The retry is for the error, never the value.
        "--output", "none",
    )


def _az_command(*args: str) -> str:
    """An `az` command line that is safe for an operator to paste into a shell.

    A reference does not only come from the operator's own keyboard — a committed
    `[sandbox.secrets]` entry is one too — and interpolating its segments raw put
    `$(…)` into text this module explicitly tells a human to run, a command
    substitution waiting for a copy-paste. Quoting makes it an argument instead.

    `_parse`'s name rules now leave nothing shell-significant in a vault or
    secret segment, so no caller can reach this with such a payload today. The
    quoting stays because the guarantee belongs to the function that builds the
    line, not to the distance between it and a check somewhere else. Ordinary
    names need no quotes, so a real failure's message is unchanged either way.
    """
    return shlex.join(["az", "keyvault", "secret", *args])


_ERROR_LINE = re.compile(r"^ERROR:\s*(?:\(([A-Za-z]+)\)\s*)?(.*)$")
_CODE_LINE = re.compile(r"^Code:\s*([A-Za-z]+)\s*$")
_INNER_CODE_LINE = re.compile(r'^\s*"code":\s*"([A-Za-z]+)"')


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


def _az_errors(stderr: str, *, hide_state: bool = False) -> str:
    """az's own ERROR: lines, joined — empty when it printed none.

    `hide_state` drops a line naming a *disabled* secret, for the paths where
    az may be describing the vault rather than the request: a disabled secret is
    reported as an absent one, and relaying az's words there would disclose the
    very difference that decision exists to hide.

    It is off by default because the caller, not this function, knows which it
    is. An invalid-request response echoes back only what the caller typed, so
    it can be relayed whole; filtering it unconditionally — as an earlier
    version did — threw away az's real reason for a reference like
    `akv://v/disabled secret` and left a message claiming az had printed no
    ERROR: line at all. `_parse` refuses that reference outright now, but the
    asymmetry it taught is the reason this parameter exists.
    """
    lines = [
        line.partition("ERROR:")[2].strip()
        for line in stderr.splitlines()
        if line.startswith("ERROR:")
        and not (hide_state and "disabled" in line.lower())
    ]
    return (" " + " ".join(lines)) if lines else ""
