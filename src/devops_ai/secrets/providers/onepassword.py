"""1Password items: `op://<vault>/<item>/<field>`, read through the `op` CLI.

The CLI carries the user's own grant; the provider adds nothing to it beyond the
process environment it is given, so `OP_ACCOUNT` and a service-account token
reach `op` exactly as they would from a shell.

Writing creates the item when it does not exist and sets the field when it does.
The value travels as a JSON item template on `op`'s standard input, for both —
`op`'s own help says to use a template rather than an assignment argument for a
sensitive value, and stdin is the one form of template that never touches disk.

Two things make a write harder than it reads. A title is not a name: 1Password
lets two items share one, and an archived item keeps its title too — so a write
answers with the *item-ID* reference, which stays pointed at what was written.
And an item template replaces the item, keeping only what it lists, so an update
is the whole item fetched, one field changed, and the whole item sent back;
a partial template silently drops every custom field it omits (measured).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from ..context import ResolveContext
from ..environ import encode_env
from ..errors import EnvironmentEncodingError, ProviderError

SCHEME = "op://"
TIMEOUT = 30
SEGMENTS = 3
NUL = "\0"
# What `op` says when nobody is signed in. Narrower than the substring `sign`
# the read path has used since M1, which also matches `assign` — so a refused
# field assignment would have been reported as a missing session. The read
# path keeps its wording: M1's behaviour is not this milestone's to move.
SIGNIN_MARKERS = ("sign in", "signed in", "signin")
# The category a created item is given, and the one agent-memory's `agent
# create` already uses. It matters beyond taste: `op item create` adds a
# category's built-in fields to whatever template it is handed, so a field
# named `password` has to be merged *into* the built-in one rather than added
# beside it — two fields of that name and `op read` returns the wrong one
# (measured). `_set_field` merges by name, which is what makes that safe.
CATEGORY = "Login"
CONCEALED = "CONCEALED"
# `op read` resolves a field by either of these, so a write has to match on
# both: a field a human created has an opaque `id` and the `label` they typed.
FIELD_NAMES = ("label", "id")
# Section fields arrive in the same flat `fields` array as top-level ones,
# distinguished only by this key — and a top-level field carries it as an
# explicit `null` rather than omitting it (measured against a real item, op
# 2.39.0). A three-segment reference addresses a *top-level* field:
# `op read op://v/item/token` returns the top-level `token` even when a section
# field shares that label, and the section one is reached by the four-segment
# form this provider refuses to write. Matching without this check would set
# both, overwriting a credential nobody named.
SECTION = "section"
# `?attribute=otp` and friends turn a reference into a request for something
# derived from a field rather than the field itself. There is nothing to store
# behind one.
ATTRIBUTE = "?"


def handles(ref: str) -> bool:
    return ref.startswith(SCHEME)


def resolve(ref: str, ctx: ResolveContext) -> str:
    """Read the item through `op`, translating its failures into guidance."""
    executable = _executable(ctx)

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
            env=encode_env(ctx.env, utf8_keys=ctx.declared),
        )
    except EnvironmentEncodingError as exc:
        raise ProviderError(str(exc)) from None
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


def write(
    ref: str, value: str, ctx: ResolveContext, if_absent: bool = False
) -> str:
    """Store the value in the item's field; answer with the item-ID reference."""
    vault, item, field = _parse(ref)
    executable = _executable(ctx)

    item_id = _find(executable, ctx, vault, item, ref)
    if item_id is None:
        document = _template(executable, ctx, ref)
        document["title"] = item
        _set_field(document, field, value)
        created = _op(
            executable, ctx, ref, "create",
            ["item", "create", "--vault", vault, "-", "--format=json"],
            json.dumps(document),
        )
        item_id = _identifier(created, ref)
    else:
        # The whole item, because `op item edit --template` keeps only the
        # fields the template lists: a template carrying just this one field
        # deletes every other custom field on the item (measured, 2026-09-13).
        # This rests on `op item get --format=json` returning concealed values
        # in the clear, which it does (measured against a real item, op 2.39.0)
        # — were a version to mask them, this would write the masks back.
        document = _document(
            executable, ctx, ref, "read",
            ["item", "get", item_id, "--vault", vault, "--format=json"],
        )
        if if_absent and _has_value(document, field):
            # The item is already in hand, so this costs nothing and answers
            # with the same id reference a write would have: a caller re-running
            # provisioning stores the same string whether or not it minted the
            # credential this time.
            return f"{SCHEME}{vault}/{item_id}/{field}"
        _set_field(document, field, value)
        _op(
            executable, ctx, ref, "update",
            ["item", "edit", item_id, "--vault", vault],
            json.dumps(document),
        )

    return f"{SCHEME}{vault}/{item_id}/{field}"


def _parse(ref: str) -> tuple[str, str, str]:
    """Split a reference into vault, item and field, or say what it should be."""
    if NUL in ref:
        # `subprocess.run` raises ValueError on a NUL in argv before `op`
        # starts, and the resolver translates only ProviderError — so this
        # would surface as a traceback rather than a sentence.
        raise ProviderError(
            "Malformed reference. A reference cannot contain a NUL byte."
        )
    parts = ref[len(SCHEME):].split("/")
    if len(parts) != SEGMENTS or not all(parts):
        raise ProviderError(
            f"Cannot write {ref}. Expected {SCHEME}<vault>/<item>/<field>; a "
            f"reference naming a section has no field of its own to write, and "
            f"a field inside a section has to be created in 1Password first."
        )
    vault, item, field = parts
    if ATTRIBUTE in field:
        raise ProviderError(
            f"Cannot write {ref}. A reference ending in {ATTRIBUTE}… asks for "
            f"something derived from a field — a one-time password, say — and "
            f"there is nothing behind it to store. Name the field itself."
        )
    return vault, item, field


def _find(
    executable: str, ctx: ResolveContext, vault: str, item: str, ref: str
) -> str | None:
    """The id of the item the reference names, or None when there is none yet.

    Asked of `op item list` rather than of `op item get`: "no such item" and
    "you cannot see that vault" are both a non-zero exit with a sentence, and
    telling them apart by matching that sentence would make creating an item
    depend on the wording of an error message. A listing answers the question
    as data — and it is the same call that proves vault access in the first
    place.

    The cost is that a write transfers the vault's item list — ids and titles,
    never values — so a run storing N secrets into a vault of M items reads
    N×M records. That is the price of not parsing an error message, and it is
    chosen rather than paid by accident: a later reader should not quietly
    turn this back into an `op item get`.

    An archived item is not in the listing, so a title that survives only in
    the archive reads here as free. That is the intended answer: the write
    creates a new item and returns *its* id, which is exactly the collision the
    id form exists to escape.
    """
    listing = _op(
        executable, ctx, ref, "list",
        ["item", "list", "--vault", vault, "--format=json"],
    )
    if not (listing.stdout or "").strip():
        # `[]` would parse as "the vault is empty", and an empty vault is a
        # vault the item is certainly not in — so a listing that said nothing
        # would become a second item, or a disarmed `--if-absent`. Measured
        # against op 2.39.0: a listing with no matches prints `[]`, never
        # nothing, so silence here is a failure and not an empty vault.
        raise ProviderError(
            f"1Password answered nothing when listing the vault for {ref}, so "
            f"whether the item exists could not be determined and nothing was "
            f"written. Check that `op item list --vault {vault}` succeeds."
        )
    try:
        items = json.loads(listing.stdout)
    except ValueError:
        raise ProviderError(
            f"1Password did not answer with JSON when listing the vault for "
            f"{ref}. Check that `op item list --vault {vault}` succeeds."
        ) from None
    if not isinstance(items, list):
        # Not an empty vault: a listing nobody could read says nothing about
        # whether the item is there. Read as empty it would create a second
        # item — and silently disarm the `--if-absent` that exists to stop
        # exactly that.
        raise ProviderError(
            f"1Password did not answer with a list of items when listing the "
            f"vault for {ref}, so whether the item exists could not be "
            f"determined and nothing was written. Check that "
            f"`op item list --vault {vault}` succeeds."
        )

    entries = [entry for entry in items if isinstance(entry, dict)]
    if any(entry.get("id") == item for entry in entries):
        return item
    titled = [
        str(entry["id"])
        for entry in entries
        if entry.get("title") == item and entry.get("id")
    ]
    if len(titled) > 1:
        raise ProviderError(
            f"{len(titled)} items in vault {vault} are titled {item}, so "
            f"{ref} does not say which one to write. Name the item by its id "
            f"instead — a write answers with that form for this reason."
        )
    return titled[0] if titled else None


def _template(executable: str, ctx: ResolveContext, ref: str) -> dict[str, Any]:
    """The empty item `op` would create for this category, as a document.

    Fetched rather than written out here, so which fields a category is born
    with stays 1Password's answer. It is what makes merging a `password` into
    the built-in field possible without this module knowing there is one.
    """
    return _document(
        executable, ctx, ref, "template",
        ["item", "template", "get", CATEGORY],
    )


def _document(
    executable: str, ctx: ResolveContext, ref: str, doing: str, args: list[str]
) -> dict[str, Any]:
    """Run `op` and parse its stdout as an item document."""
    result = _op(executable, ctx, ref, doing, args)
    if not (result.stdout or "").strip():
        # `{}` would parse, and that is the danger: an update rebuilds the
        # whole item from this document, so an empty one becomes a template
        # holding just the field being written — and `op item edit` drops every
        # field a template omits. A one-field write would wipe the rest.
        raise ProviderError(
            f"1Password answered nothing for {ref} (op item {doing}), so there "
            f"is no item to write back and nothing was written."
        )
    try:
        document = json.loads(result.stdout)
    except ValueError:
        # Never the output itself: for `item get` it is the item, values and
        # all, and a parse failure is the one moment nobody has checked it.
        raise ProviderError(
            f"1Password did not answer with JSON for {ref} (op item {doing})."
        ) from None
    if not isinstance(document, dict):
        raise ProviderError(
            f"1Password did not answer with an item for {ref} (op item {doing})."
        )
    return document


def _set_field(document: dict[str, Any], field: str, value: str) -> None:
    """Set `field` in the document, adding it only when the item has none.

    Every field of that name is set, not just the first. An item can carry two
    — a built-in `password` and a custom one, which is what a naive create
    produces — and `op read` then picks one of them without saying which. Where
    that has already happened, setting both is what makes the read that follows
    return this value rather than a coin toss.
    """
    if not isinstance(document.get("fields"), list):
        document["fields"] = []
    fields = document["fields"]
    matched = _named(document, field)
    for entry in matched:
        entry["value"] = value
    if not matched:
        fields.append(
            {"id": field, "type": CONCEALED, "label": field, "value": value}
        )


def _has_value(document: dict[str, Any], field: str) -> bool:
    """Whether the item already carries something under that name.

    An empty string is not something: `op item create` gives a Login item its
    built-in `username` and `password` fields with no value at all, and a
    reference to one of those names an empty slot rather than a secret. Writing
    into it is what `--if-absent` is for.
    """
    return any(entry.get("value") for entry in _named(document, field))


def _named(document: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """The item's top-level fields that the reference's last segment names."""
    return [
        entry
        for entry in _fields(document)
        if not entry.get(SECTION)
        and any(entry.get(name) == field for name in FIELD_NAMES)
    ]


def _fields(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The item's fields, whatever `op` put under that key."""
    fields = document.get("fields")
    if not isinstance(fields, list):
        return []
    return [entry for entry in fields if isinstance(entry, dict)]


def _identifier(created: subprocess.CompletedProcess[str], ref: str) -> str:
    """The id `op item create` reported, which is what a caller should keep."""
    try:
        document = json.loads(created.stdout or "{}")
        item_id = document["id"]
    except (ValueError, KeyError, TypeError):
        raise ProviderError(
            f"1Password created the item for {ref} but did not report its id, "
            f"so there is no reference to hand back. Find it with: "
            f"op item list --vault {ref[len(SCHEME):].split('/')[0]}"
        ) from None
    return str(item_id)


def _executable(ctx: ResolveContext) -> str:
    """The `op` to run, found on the PATH the child will be given.

    The child is spawned with `env=ctx.env`, and exec resolves the program on
    *that* environment's PATH — including its fallback when the variable is
    absent. Resolving here on the same PATH and handing the child the absolute
    path means there is no second search that could disagree with this one.
    """
    executable = shutil.which("op", path=ctx.env.get("PATH", os.defpath))
    if executable is None:
        raise ProviderError(
            "1Password CLI (op) not found. "
            "Install: brew install 1password-cli "
            "— or use $VAR references instead."
        )
    return executable


def _op(
    executable: str,
    ctx: ResolveContext,
    ref: str,
    doing: str,
    args: list[str],
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """One `op` call, with its failures turned into sentences.

    Nothing of `op`'s stderr reaches the caller. On the calls that carry a
    template, what was sent *is* the secret, and a tool that reports what it
    could not parse would be reporting part of it; rather than judge which
    calls are safe to quote, none are, and the message says which `op` command
    to run by hand to see its own words.
    """
    try:
        result = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT,
            input=stdin,
            env=encode_env(ctx.env, utf8_keys=ctx.declared),
        )
    except EnvironmentEncodingError as exc:
        raise ProviderError(str(exc)) from None
    except subprocess.TimeoutExpired:
        raise ProviderError(
            f"1Password CLI timed out ({doing}) for {ref}. A prompt may be "
            f"waiting for you; try: eval $(op signin)"
        ) from None

    if result.returncode != 0:
        stderr = (result.stderr or "").lower()
        if any(marker in stderr for marker in SIGNIN_MARKERS):
            raise ProviderError(
                f"1Password not authenticated, so {ref} was not written. "
                f"Run: eval $(op signin)"
            )
        # Everything else — a refused vault, an item somebody else locked —
        # falls to the sentence below, which sends the reader to their access
        # rather than to a session that is already fine.
        raise ProviderError(
            f"1Password refused to {doing} for {ref}. Run "
            f"`op {' '.join(args[:2])} --help` and check the vault, the item "
            f"and your access to them."
        )
    return result
