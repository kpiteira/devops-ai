"""An OpenBao / HashiCorp Vault KV v2 key: `bao://<mount>/<path>#<key>`.

Spoken over HTTP with the standard library rather than through the `bao` binary:
a container that has `ksecret` and a token should not need a second CLI to read
one value. Where and who come from the environment the same way `bao` takes
them — the `BAO_*` spelling first, then `VAULT_*`, then the token file
`bao login` writes — so the two agree on which server they are talking to.

Two rules hold everywhere below. Nothing that answers back carries a value: a
missing key is named, its siblings are not, and a server error is reported by
status rather than by echoing a response body. And the token goes only to the
address that was configured — no redirect is ever followed, and an ambient
`HTTP_PROXY` is not used, because urllib would carry the token header to both.
"""

from __future__ import annotations

import http.client
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

from ..context import ResolveContext
from ..errors import ProviderError

SCHEME = "bao://"
KEY_SEPARATOR = "#"
ADDRESS_VARS = ("BAO_ADDR", "VAULT_ADDR")
TOKEN_VARS = ("BAO_TOKEN", "VAULT_TOKEN")
CACERT_VARS = ("BAO_CACERT", "VAULT_CACERT")
TOKEN_FILE = ".vault-token"
# What `http.client` encodes a header value as; anything else cannot be sent.
HEADER_ENCODING = "latin-1"
# urlopen speaks more than the web: an address typo'd into a `file:` URL would
# otherwise read a local path and hand it back as a secret.
NETWORK_URL_SCHEMES = frozenset({"http", "https"})
TRAVERSAL = frozenset({".", ".."})
TIMEOUT = 30
# Every 3xx, not an enumerated few: which ones urllib would have followed is
# exactly the judgement this provider declines to make.
REDIRECT_MIN, REDIRECT_MAX = 300, 400


class Server(NamedTuple):
    """Where to ask, and which variable said so.

    Both spellings are supported, so guidance that names the wrong one sends the
    user to a variable they never set.
    """

    variable: str
    base: str


def handles(ref: str) -> bool:
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Read one key of the current version of a KV v2 secret."""
    mount, path, key = _parse(ref)
    server = _address(ctx)
    token = _token(ctx)

    values = _read_secret(server, mount, path, ref, token, _tls(ctx))
    if key not in values:
        raise ProviderError(f"Key {key} not found in the secret at {mount}/{path}.")
    value = values[key]
    # The `bao` CLI writes strings, but the API stores arbitrary JSON, so a
    # number or a boolean is possible. Render it as it was stored rather than
    # refuse a secret the user can plainly see in their vault.
    return value if isinstance(value, str) else json.dumps(value)


def _parse(ref: str) -> tuple[str, str, str]:
    """Split a reference into mount, path and key, or say what it should be."""
    location, separator, key = ref[len(SCHEME):].partition(KEY_SEPARATOR)
    mount, slash, path = location.partition("/")
    traversal = TRAVERSAL.intersection(location.split("/"))
    if not (mount and slash and path and separator and key) or traversal:
        # `..` would be cleaned by the server and answered with a redirect to a
        # path outside the named mount; refusing it here keeps the reference
        # meaning what it reads as.
        raise ProviderError(
            f"Malformed reference {ref}. Expected "
            f"{SCHEME}<mount>/<path>{KEY_SEPARATOR}<key>."
        )
    return mount, path, key


def _address(ctx: ResolveContext) -> Server:
    """The server to ask, `BAO_ADDR` before `VAULT_ADDR` as the `bao` CLI does."""
    for name in ADDRESS_VARS:
        value = ctx.env.get(name, "").strip()
        if not value:
            continue
        try:
            parts = urllib.parse.urlsplit(value)
            usable = (
                parts.scheme in NETWORK_URL_SCHEMES
                # `hostname`, not `netloc`: `http://:8200` has a netloc and a
                # good port but names no host, and urllib reads an empty host
                # as localhost — presenting the token to a server the address
                # never named, which is the one thing this module decides.
                and bool(parts.hostname)
                and _port_is_a_port(parts)
                # Userinfo survives in `netloc`, and the address it belongs to
                # is named in the sentences this module raises. A password in
                # `BAO_ADDR` must not reach stderr on the first failed connect.
                and "@" not in parts.netloc
                and not parts.query
                and not parts.fragment
            )
        except ValueError:
            # An unbalanced bracket ("Invalid IPv6 URL") — a typo, not a crash.
            usable = False
        if not usable:
            # The address is not echoed back: it is what may be carrying a
            # credential, and naming the variable is enough to fix it.
            raise ProviderError(
                f"{name} is not a server address: it must be an http or https "
                f"URL naming a host, with no credentials, query or fragment."
            )
        # Rebuilt from the parts rather than returned raw, so nothing but the
        # server's own base can survive into the URL the reference builds.
        return Server(
            name, f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
        )
    raise ProviderError(
        "No OpenBao server address. Export BAO_ADDR (or VAULT_ADDR) with the "
        "address of your server."
    )


def _port_is_a_port(parts: urllib.parse.SplitResult) -> bool:
    """Whether the authority's port is one, since `.port` parses only on access.

    `:99999` and `:abc` both leave `urlsplit` happy and raise from this property
    instead. Unvalidated they travel to `getaddrinfo`, which answers that the
    *name* could not be resolved — a sentence about the wrong half of the
    address, from the function whose job is saying which half is wrong.

    Port 0 is excluded for the same reason: it is the "pick me one" bind port,
    never a destination, and reaches the user as an errno about assigning an
    address rather than as the address guidance this exists to give.
    """
    try:
        return parts.port is None or 0 < parts.port <= 65535
    except ValueError:
        return False


def _token(ctx: ResolveContext) -> str:
    """The token to present: env before the file `bao login` writes."""
    for name in TOKEN_VARS:
        value = ctx.env.get(name, "").strip()
        if value:
            return _sendable(value, name)

    home = _home(ctx)
    path = home / TOKEN_FILE if home is not None else None
    if path is not None:
        try:
            from_file = path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, NotADirectoryError):
            # The only two ways the file is simply not there. Asking
            # `path.exists()` first would have been the same question with a
            # worse answer: it swallows exactly these and propagates the rest,
            # so a home the user cannot stat into raised `PermissionError` out
            # of the check itself, ahead of the handler written for it.
            from_file = ""
        except (OSError, UnicodeDecodeError) as exc:
            # Distinct from "no token": the file is there and unusable, and
            # "log in again" is only the right advice once you know that.
            raise ProviderError(
                f"Cannot read the token file {path}: {_reason(exc)}. "
                f"Run `bao login` (or `vault login`) to rewrite it."
            ) from None
        if from_file:
            return _sendable(from_file, str(path))

    where = f", which writes {path}" if path is not None else ""
    raise ProviderError(
        f"No OpenBao or Vault token. Run `bao login` (or `vault login`)"
        f"{where}, or export BAO_TOKEN (or VAULT_TOKEN)."
    )


def _sendable(token: str, source: str) -> str:
    """A token becomes a header value, and a header value is narrow.

    `http.client` refuses both a line break and anything outside latin-1 — the
    first with the token in the exception text, the second with the offending
    character in it. Either would also surface from inside `_read_secret`'s
    `ValueError` handler as "the server did not answer with JSON", which is a
    sentence about a request that was never sent. Refusing here keeps the value
    out of any handler further out and names which of the three sources needs
    fixing.
    """
    unusable = ""
    if "\r" in token or "\n" in token:
        unusable = "a line break"
    else:
        try:
            token.encode(HEADER_ENCODING)
        except UnicodeEncodeError:
            unusable = f"a character outside {HEADER_ENCODING}"
    if unusable:
        raise ProviderError(
            f"The token from {source} contains {unusable}, so it cannot be "
            f"sent in an HTTP header. Run `bao login` (or `vault login`) to "
            f"replace it."
        )
    return token


def _home(ctx: ResolveContext) -> Path | None:
    """The home of the environment being resolved in, and only that.

    `Path.home()` would fall back to the process environment, which would make
    this the one input the module reads from somewhere other than `ctx.env` —
    the same inconsistency the empty `ProxyHandler` exists to remove. Every
    real caller carries `HOME` already (`ResolveContext` defaults its env to
    `os.environ`, and `layered_env` copies it), so the only context this
    changes is a deliberately sanitised one, which should not reach an ambient
    `~/.vault-token`. None means the token file is one more place the token is
    not.
    """
    home = ctx.env.get("HOME", "").strip()
    return Path(home) if home else None


def _tls(ctx: ResolveContext) -> ssl.SSLContext | None:
    """The trust store to verify with: the system's, or `BAO_CACERT`'s bundle.

    A homelab vault is commonly served by a private CA, and `bao` is pointed at
    its bundle by exactly these variables. Only the trust anchor is honored —
    nothing here can be made to skip verification.
    """
    for name in CACERT_VARS:
        cafile = ctx.env.get(name, "").strip()
        if not cafile:
            continue
        try:
            return ssl.create_default_context(cafile=cafile)
        except OSError as exc:
            raise ProviderError(
                f"Cannot read the CA bundle named by {name} ({cafile}): "
                f"{_reason(exc)}."
            ) from None
    return None


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect rather than deciding which ones are safe.

    Following a 3xx means judging, per hop, whether the location it names may
    be handed a vault token — the scheme, the host, the port, and whatever the
    next hop says after that. That is attack surface out of proportion to what
    this provider is for (Karl's call, 2026-09-13), and urllib copies the
    request's headers onto the redirected request, so a wrong judgement hands
    the token over silently. Returning None here means every 3xx surfaces as
    its own status instead.
    """

    def redirect_request(  # type: ignore[no-untyped-def]
        self, req, fp, code, msg, headers, newurl
    ):
        return None


def _read_secret(
    server: Server,
    mount: str,
    path: str,
    ref: str,
    token: str,
    tls: ssl.SSLContext | None,
) -> dict[str, object]:
    """GET the current version of `<mount>/<path>`; return its key/value map."""
    location = urllib.parse.quote(f"{mount}/data/{path}", safe="/")
    request = urllib.request.Request(
        f"{server.base}/v1/{location}",
        headers={"X-Vault-Token": token},
        method="GET",
    )
    opener = urllib.request.build_opener(
        # An empty ProxyHandler, not the default one: `build_opener` would
        # otherwise install a handler that reads `HTTP_PROXY` from the process
        # environment — not from `ctx.env`, which is where everything else here
        # comes from — and send the token header to that proxy instead of to
        # the server the reference named.
        urllib.request.ProxyHandler({}),
        _NoRedirects(),
        *([urllib.request.HTTPSHandler(context=tls)] if tls is not None else []),
    )
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        # HTTPError *is* the response: raising past it without closing leaves a
        # socket open for as long as the error is held, and `resolve_all` holds
        # every one of them.
        exc.close()
        raise _status_error(exc.code, ref, mount, path, server) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        # HTTPException is not an OSError: a truncated body raises
        # `IncompleteRead` out of `.read()`, which would otherwise leave the
        # provider as a traceback rather than a sentence.
        raise ProviderError(
            f"Cannot reach the server at {server.base}: {_reason(exc)}."
        ) from None
    except ValueError:
        # JSONDecodeError and UnicodeDecodeError both land here: a body that is
        # not UTF-8 is no more JSON than one that is not parseable.
        raise ProviderError(
            f"The server at {server.base} did not answer with JSON. Check that "
            f"{server.variable} names an OpenBao or Vault server."
        ) from None

    envelope = body.get("data") if isinstance(body, dict) else None
    if not isinstance(envelope, dict) or "data" not in envelope:
        raise ProviderError(
            f"The answer for {mount}/{path} is not a KV v2 secret. Check that "
            f"{mount} is a KV v2 mount."
        )
    values = envelope["data"]
    if values is None:
        # The one shape KV v2 defines for this: the current version was
        # deleted or destroyed. Anything else non-dict is a malformed answer,
        # and telling that user their version was deleted would be a wrong
        # remediation for a server problem.
        raise ProviderError(
            f"The secret at {mount}/{path} has no readable current version "
            f"(the latest version is deleted or destroyed)."
        )
    if not isinstance(values, dict):
        raise ProviderError(
            f"The answer for {mount}/{path} is not a KV v2 secret. Check that "
            f"{mount} is a KV v2 mount."
        )
    return values


def _status_error(
    code: int,
    ref: str,
    mount: str,
    path: str,
    server: Server,
) -> ProviderError:
    """What an HTTP status means, without reading the body back to the user.

    Both spellings are supported everywhere, so remediation that names only one
    sends half the users to a variable they never set. Where the answer depends
    on which was chosen, `server.variable` says; where it does not, both are
    named, matching how `_token` already asks for one.
    """
    if code in (401, 403):
        return ProviderError(
            f"The server refused the token for {ref} (HTTP {code}). Run "
            f"`bao login` (or `vault login`), or export a BAO_TOKEN (or "
            f"VAULT_TOKEN) with read access."
        )
    if code == 404:
        return ProviderError(
            f"No secret at {mount}/{path}. Check the mount and path in {ref}."
        )
    if code == 503:
        return ProviderError(
            f"The server is sealed or standing by (HTTP {code}); it cannot "
            f"answer for {ref} yet."
        )
    if REDIRECT_MIN <= code < REDIRECT_MAX:
        return ProviderError(
            f"The server answered {ref} with a redirect (HTTP {code}), and a "
            f"redirect is never followed — the token goes only to the address "
            f"that was configured. Point {server.variable} at the server that "
            f"holds the secret."
        )
    return ProviderError(f"The server returned HTTP {code} for {ref}.")


def _reason(exc: BaseException) -> str:
    """Why something failed, in the terms the exception has — never its input."""
    if isinstance(exc, UnicodeDecodeError):
        # `.reason` is "invalid start byte", which describes a byte rather than
        # the file. `envfile` settled on this wording for the same failure.
        return "not valid UTF-8 text"
    reason = getattr(exc, "reason", None)
    if reason is None:
        reason = getattr(exc, "strerror", None)
    return str(reason) if reason else exc.__class__.__name__
