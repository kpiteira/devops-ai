"""Store a secret at a reference, through whatever provider claims it.

The mirror of `resolver.resolve`, and discovery works the same way: this module
names no scheme and no provider module. What it adds is the *canonical*
reference — the string a caller should keep. For most providers that is the
reference it passed in; for 1Password it is not, because a title can come to
mean a different item later, so the provider answers with the form that cannot.

Writing is narrower than reading on purpose. A value arrives as text and is
handed to the provider, which decides how it reaches the backend — stdin, or a
file only its own process can open. Nothing here builds a command line, so
nothing here can put a secret in one.
"""

from __future__ import annotations

from .context import ResolveContext
from .errors import ProviderError
from .resolver import provider_for

# What a provider that can store a value exports. Read off the provider rather
# than listed anywhere, so a backend added tomorrow is writable by writing it
# and read-only by not — the same shape the resolver uses to discover providers
# in the first place.
WRITE = "write"

# A NUL cannot survive exec, and a line break cannot survive the promise that
# stdout is one line. `str.splitlines()` itself rather than a list of
# characters: it splits on `\v`, `\f`, `\x1c`, `\x85` and `\u2028` too, and the
# answer this module makes is only one line if every one of them is absent.
NUL = "\0"


def _visible(ref: str) -> str:
    """The reference with only its unprintable characters escaped.

    A reference nobody vetted is about to be named in a message a human reads,
    and echoing a raw line break hides the very thing the message is about.
    """
    return "".join(
        char if char.isprintable() else char.encode("unicode_escape").decode("ascii")
        for char in ref
    )


def write(
    ref: str,
    value: str,
    ctx: ResolveContext | None = None,
    if_absent: bool = False,
) -> str:
    """Store `value` at `ref`; return the reference a caller should keep.

    `if_absent` leaves a secret that is already there alone, and still answers
    with its reference — what a provisioning step re-run on an existing
    deployment needs, where minting a second credential is the failure. Each
    provider answers the question against its own backend rather than this
    module resolving first: a read that fails for a reason other than absence
    must not be mistaken for permission to overwrite.

    Raises `ProviderError` with a sentence that names the reference and never
    the value.
    """
    context = ctx if ctx is not None else ResolveContext()
    provider = provider_for(ref)
    if provider is None:
        # The reference is deliberately not quoted back. A string no provider
        # claims is a literal, and a literal *is* its value — echoing it here
        # would leak exactly what a bare `read` is forbidden to print.
        raise ProviderError(
            "That is not a secret reference, so there is nothing to write it "
            "to: no provider claims it, which makes it a literal — a value "
            "already, standing for nothing else. Name a reference whose scheme "
            "a provider handles."
        )
    # After the literal branch, never before it: a string no provider claims is
    # its own value, and naming it here would leak exactly what that branch
    # keeps quiet. Before the read-only branch, which echoes the reference.
    #
    # Here rather than in each provider because the one line this refuses to
    # break is the *canonical reference*, which is this module's promise and no
    # backend's. Left to the providers it went the way such things go: `dotenv`
    # and `azurekeyvault` each grew a guard, `openbao` and `onepassword` never
    # did, and `openbao` answers with the reference it was handed — so a write
    # succeeded, stored the value, and returned two lines (measured against a
    # stub KV v2 server, 2026-09-14). Reads are untouched: nothing resolving a
    # reference passes through here, so the M1-M3 invariant holds.
    if NUL in ref or ref.splitlines() != [ref]:
        raise ProviderError(
            f"Malformed reference {_visible(ref)}, so nothing was written. A "
            f"reference cannot contain a NUL byte or a line break: the "
            f"reference this command answers with is one line."
        )
    writer = getattr(provider, WRITE, None)
    if writer is None:
        # The reference, not just its scheme: a caller writing several of them
        # needs to know which one was refused, and naming a reference is safe
        # here in a way naming a literal is not — a literal has no provider, so
        # it never reaches this branch.
        raise ProviderError(
            f"{provider.SCHEME} references cannot be written, so {ref} was "
            f"not stored; this provider only reads."
        )
    return str(writer(ref, value, context, if_absent))
