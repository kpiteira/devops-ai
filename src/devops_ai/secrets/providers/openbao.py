"""An OpenBao / HashiCorp Vault KV v2 key: `bao://<mount>/<path>#<key>`.

Spoken over HTTP with the standard library rather than through the `bao` binary:
a container that has `ksecret` and a token should not need a second CLI to read
one value. The server address and the token come from the environment exactly
the way the `bao` CLI takes them — the `BAO_*` spelling first, then `VAULT_*`,
then the token file `bao login` writes — so the two agree on which server they
are talking to.

Nothing here ever puts a value in a message: a missing key is named, its
siblings are not, and a server error is reported by status, never by echoing a
response body.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "bao://"
KEY_SEPARATOR = "#"
ADDRESS_VARS = ("BAO_ADDR", "VAULT_ADDR")
TOKEN_VARS = ("BAO_TOKEN", "VAULT_TOKEN")
TOKEN_FILE = ".vault-token"
# urlopen speaks more than the web: an address typo'd into a `file:` URL would
# otherwise read a local path and hand it back as a secret.
NETWORK_URL_SCHEMES = frozenset({"http", "https"})
TIMEOUT = 30


def handles(ref: str) -> bool:
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Read one key of the current version of a KV v2 secret."""
    mount, path, key = _parse(ref)
    address = _address(ctx)
    token = _token(ctx)

    values = _read_secret(address, mount, path, ref, token)
    if key not in values:
        raise ProviderError(f"Key {key} not found in the secret at {mount}/{path}.")
    value = values[key]
    # KV v2 holds arbitrary JSON; `bao kv put` only ever writes strings. A
    # number or a boolean is rendered as it was stored rather than refused.
    return value if isinstance(value, str) else json.dumps(value)


def _parse(ref: str) -> tuple[str, str, str]:
    """Split a reference into mount, path and key, or say what it should be."""
    location, separator, key = ref[len(SCHEME):].partition(KEY_SEPARATOR)
    mount, slash, path = location.partition("/")
    if not (mount and slash and path and separator and key):
        raise ProviderError(
            f"Malformed reference {ref}. Expected "
            f"{SCHEME}<mount>/<path>{KEY_SEPARATOR}<key>."
        )
    return mount, path, key


def _address(ctx: ResolveContext) -> str:
    """The server to ask, `BAO_ADDR` before `VAULT_ADDR` as the `bao` CLI does."""
    for name in ADDRESS_VARS:
        value = ctx.env.get(name, "").strip()
        if not value:
            continue
        parts = urllib.parse.urlsplit(value)
        if parts.scheme not in NETWORK_URL_SCHEMES or not parts.netloc:
            raise ProviderError(
                f"{name} is not a server address: it must be an http or https "
                f"URL naming a host."
            )
        return value.rstrip("/")
    raise ProviderError(
        "No OpenBao server address. Export BAO_ADDR (or VAULT_ADDR) with the "
        "address of your server."
    )


def _token(ctx: ResolveContext) -> str:
    """The token to present: env before the file `bao login` writes."""
    for name in TOKEN_VARS:
        value = ctx.env.get(name, "").strip()
        if value:
            return value

    path = _home(ctx) / TOKEN_FILE
    try:
        from_file = path.read_text().strip()
    except OSError:
        from_file = ""
    if not from_file:
        raise ProviderError(
            f"No OpenBao token. Run `bao login`, which writes {path}, or "
            f"export BAO_TOKEN (or VAULT_TOKEN)."
        )
    return from_file


def _home(ctx: ResolveContext) -> Path:
    """The home directory of the environment being resolved in, not the process's."""
    home = ctx.env.get("HOME", "").strip()
    return Path(home) if home else Path.home()


def _read_secret(
    address: str, mount: str, path: str, ref: str, token: str
) -> dict[str, object]:
    """GET the current version of `<mount>/<path>`; return its key/value map."""
    location = urllib.parse.quote(f"{mount}/data/{path}", safe="/")
    request = urllib.request.Request(
        f"{address}/v1/{location}",
        headers={"X-Vault-Token": token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise _status_error(exc.code, ref, mount, path) from None
    except (urllib.error.URLError, OSError) as exc:
        raise ProviderError(
            f"Cannot reach the OpenBao server at {address}: {_reason(exc)}."
        ) from None
    except json.JSONDecodeError:
        raise ProviderError(
            f"The server at {address} did not answer with JSON. Check that "
            f"BAO_ADDR names an OpenBao server."
        ) from None

    envelope = body.get("data") if isinstance(body, dict) else None
    if not isinstance(envelope, dict) or "data" not in envelope:
        raise ProviderError(
            f"The answer for {mount}/{path} is not a KV v2 secret. Check that "
            f"{mount} is a KV v2 mount."
        )
    values = envelope["data"]
    if not isinstance(values, dict):
        raise ProviderError(
            f"The secret at {mount}/{path} has no readable current version "
            f"(the latest version is deleted or destroyed)."
        )
    return values


def _status_error(code: int, ref: str, mount: str, path: str) -> ProviderError:
    """What an HTTP status means, without reading the body back to the user."""
    if code in (401, 403):
        return ProviderError(
            f"OpenBao refused the token for {ref} (HTTP {code}). Run "
            f"`bao login`, or export a BAO_TOKEN with read access."
        )
    if code == 404:
        return ProviderError(
            f"No secret at {mount}/{path}. Check the mount and path in {ref}."
        )
    if code == 503:
        return ProviderError(
            f"The OpenBao server is sealed or standing by (HTTP {code}); it "
            f"cannot answer for {ref} yet."
        )
    return ProviderError(f"OpenBao returned HTTP {code} for {ref}.")


def _reason(exc: BaseException) -> str:
    """Why a connection failed, in the terms the exception has."""
    reason = getattr(exc, "reason", None)
    if reason is None:
        reason = getattr(exc, "strerror", None)
    return str(reason) if reason else exc.__class__.__name__
