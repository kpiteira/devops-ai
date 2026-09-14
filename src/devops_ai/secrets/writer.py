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
