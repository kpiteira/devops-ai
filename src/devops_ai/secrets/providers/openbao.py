"""An OpenBao / HashiCorp Vault KV v2 key: `bao://<mount>/<path>#<key>`.

Spoken over HTTP with the standard library rather than through the `bao` binary:
a container that has `ksecret` and a token should not need a second CLI to read
one value. Where and who come from the environment the same way `bao` takes
them — the `BAO_*` spelling first, then `VAULT_*`, then the token file
`bao login` writes — so the two agree on which server they are talking to.

Two rules hold everywhere below. Nothing that answers back carries a value: a
missing key is named, its siblings are not, and a server error is reported by
status rather than by echoing a response body. And the token goes only to the
server the user named: a redirect off that server is refused rather than
followed, because urllib copies request headers onto the new request.
"""

from __future__ import annotations

import http.client
import json
import ssl
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
CACERT_VARS = ("BAO_CACERT", "VAULT_CACERT")
TOKEN_FILE = ".vault-token"
# urlopen speaks more than the web: an address typo'd into a `file:` URL would
# otherwise read a local path and hand it back as a secret.
NETWORK_URL_SCHEMES = frozenset({"http", "https"})
TRAVERSAL = frozenset({".", ".."})
TIMEOUT = 30


def handles(ref: str) -> bool:
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Read one key of the current version of a KV v2 secret."""
    mount, path, key = _parse(ref)
    address = _address(ctx)
    token = _token(ctx)

    values = _read_secret(address, mount, path, ref, token, _tls(ctx))
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


def _address(ctx: ResolveContext) -> str:
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
        return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
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
    """
    try:
        return parts.port is None or 0 <= parts.port <= 65535
    except ValueError:
        return False


def _token(ctx: ResolveContext) -> str:
    """The token to present: env before the file `bao login` writes."""
    for name in TOKEN_VARS:
        value = ctx.env.get(name, "").strip()
        if value:
            return _single_line(value, name)

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
                f"Cannot read the OpenBao token file {path}: {_reason(exc)}. "
                f"Run `bao login` to rewrite it."
            ) from None
        if from_file:
            return _single_line(from_file, str(path))

    where = f", which writes {path}" if path is not None else ""
    raise ProviderError(
        f"No OpenBao token. Run `bao login`{where}, or export BAO_TOKEN "
        f"(or VAULT_TOKEN)."
    )


def _single_line(token: str, source: str) -> str:
    """A token becomes a header value, and a header value has no line breaks.

    `http.client` raises on one — with the token in the exception text. Catching
    it here keeps that value out of any handler further out, and says which of
    the three sources needs fixing.
    """
    if "\r" in token or "\n" in token:
        raise ProviderError(
            f"The OpenBao token from {source} contains a line break, so it "
            f"cannot be sent. Run `bao login` to replace it."
        )
    return token


def _home(ctx: ResolveContext) -> Path | None:
    """The home of the environment being resolved in, not the process's.

    None when there is no home to speak of: `Path.home()` raises where HOME is
    unset and the user has no passwd entry, which is an ordinary container. The
    token file is then simply one more place the token is not.
    """
    home = ctx.env.get("HOME", "").strip()
    if home:
        return Path(home)
    try:
        return Path.home()
    except RuntimeError:
        return None


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
                f"Cannot read the CA bundle {name} names ({cafile}): "
                f"{_reason(exc)}."
            ) from None
    return None


class _SameServerRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only while it stays on the server the user named.

    urllib copies the request's headers onto the redirected request, so the
    default handler would present `X-Vault-Token` to whatever host a `Location`
    names. A server's own path cleanup still resolves; a hop to another host
    does not, and surfaces as the redirect status instead.
    """

    def redirect_request(  # type: ignore[no-untyped-def]
        self, req, fp, code, msg, headers, newurl
    ):
        if _origin(newurl) != _origin(req.full_url):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _origin(url: str) -> tuple[str, str]:
    """Scheme and authority — what decides whether the token may travel."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return ("", url)
    return (parts.scheme.lower(), parts.netloc.lower())


def _read_secret(
    address: str,
    mount: str,
    path: str,
    ref: str,
    token: str,
    tls: ssl.SSLContext | None,
) -> dict[str, object]:
    """GET the current version of `<mount>/<path>`; return its key/value map."""
    location = urllib.parse.quote(f"{mount}/data/{path}", safe="/")
    request = urllib.request.Request(
        f"{address}/v1/{location}",
        headers={"X-Vault-Token": token},
        method="GET",
    )
    opener = urllib.request.build_opener(
        _SameServerRedirects(),
        *([urllib.request.HTTPSHandler(context=tls)] if tls is not None else []),
    )
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise _status_error(exc.code, ref, mount, path) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        # HTTPException is not an OSError: a truncated body raises
        # `IncompleteRead` out of `.read()`, which would otherwise leave the
        # provider as a traceback rather than a sentence.
        raise ProviderError(
            f"Cannot reach the OpenBao server at {address}: {_reason(exc)}."
        ) from None
    except ValueError:
        # JSONDecodeError and UnicodeDecodeError both land here: a body that is
        # not UTF-8 is no more JSON than one that is not parseable.
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
    if code in (301, 302, 303, 307, 308):
        return ProviderError(
            f"The server redirected {ref} to a different host (HTTP {code}), "
            f"which a token must not follow. Point BAO_ADDR at the server that "
            f"holds the secret."
        )
    return ProviderError(f"OpenBao returned HTTP {code} for {ref}.")


def _reason(exc: BaseException) -> str:
    """Why something failed, in the terms the exception has — never its input."""
    reason = getattr(exc, "reason", None)
    if reason is None:
        reason = getattr(exc, "strerror", None)
    return str(reason) if reason else exc.__class__.__name__
