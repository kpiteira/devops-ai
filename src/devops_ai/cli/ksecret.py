"""ksecret CLI — resolve secret references, and run commands with them injected.

Four verbs, one set of providers. `read` answers about a single reference and
prints its value only when asked to. `run` puts resolved values in a child's
environment and writes nothing to disk. `check` reports what resolves without
ever showing a value. `write` takes a value on stdin — never as an argument,
where the process table would carry it — and stores it at a reference.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from devops_ai.config import find_project_root, load_config
from devops_ai.secrets import (
    ERROR,
    CheckResult,
    EnvironmentEncodingError,
    ProviderError,
    ResolveContext,
    SecretResolutionError,
    context_for,
    encode_env,
    provider_for,
    read_env_file,
    resolve,
    resolve_all,
)
from devops_ai.secrets import (
    check as check_ref,
)
from devops_ai.secrets import (
    write as write_secret,
)
from devops_ai.worktree import main_repo_root

LITERAL_LABEL = "(literal)"

app = typer.Typer(
    name="ksecret",
    help="Resolve secret references through pluggable providers.",
    no_args_is_help=True,
    # A resolved value lives in a frame local. Typer's rich traceback renders
    # frame locals, which would print secrets to stderr on any unhandled error.
    pretty_exceptions_show_locals=False,
)


@app.command()
def read(
    ref: str = typer.Argument(help="Secret reference, or literal text"),
    print_value: bool = typer.Option(
        False, "--print", "-p", help="Print the value on stdout"
    ),
    no_newline: bool = typer.Option(
        False, "--no-newline", help="Omit the trailing newline after the value"
    ),
) -> None:
    """Resolve one reference; confirm it, or print it with --print."""
    try:
        value = resolve(ref, ref, ResolveContext())
    except SecretResolutionError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1) from None

    if print_value:
        _emit(value if no_newline else f"{value}\n")
    else:
        _emit(f"ok {_label(ref)}\n")
    raise typer.Exit(0)


@app.command()
def write(
    ref: str = typer.Argument(help="Secret reference to store the value at"),
    if_absent: bool = typer.Option(
        False,
        "--if-absent",
        help="Leave a secret that already exists alone, and print its reference",
    ),
) -> None:
    """Store the value on stdin at a reference; print the canonical reference."""
    try:
        value = _stdin_value()
    except ValueError as exc:
        # Named through `_label`, never as the bare `ref`: a string no provider
        # claims *is* its value, so echoing it here would leak the very thing
        # the rest of this command refuses to print. A provisioning log holding
        # many writes otherwise cannot tell which one refused its input.
        typer.echo(f"ksecret write {_label(ref)}: {exc}", err=True)
        raise typer.Exit(1) from None

    try:
        canonical = write_secret(ref, value, ResolveContext(), if_absent)
    except ProviderError as exc:
        typer.echo(f"ksecret write: {exc}", err=True)
        raise typer.Exit(1) from None

    # The reference, and only ever the reference: for `op://` it is not the one
    # that was passed in, and it is what a caller should store from here on.
    _emit(f"{canonical}\n")
    raise typer.Exit(0)


def _stdin_value() -> str:
    """The value to store: stdin's bytes as UTF-8, less one trailing newline.

    Read as bytes rather than through `sys.stdin`, whose decoder follows the
    locale — under the `LC_ALL=C` of a container or a cron job, a text read
    would fail on a non-ASCII value and say which character it choked on. One
    trailing newline goes, because `printf '%s\\n'` and every shell pipeline
    put one there; a second one is part of the value, and providers that cannot
    store a line break say so themselves.

    Stripping before the decode is safe whatever the bytes are: UTF-8 is
    self-synchronising, so a trailing `0A` is a newline and never the tail of
    some other character.
    """
    if sys.stdin.isatty():
        # Without this the command is indistinguishable from a hang: nothing
        # has been printed, and stdin is a terminal nobody has been asked to
        # type into. On stderr, so the one line on stdout is still the
        # reference and a pipeline is unaffected — and only when there is a
        # person there to read it.
        typer.echo(
            "ksecret write: reading the value from stdin; end it with Ctrl-D.",
            err=True,
        )
    stream = getattr(sys.stdin, "buffer", None)
    raw = stream.read() if stream is not None else sys.stdin.read().encode("utf-8")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # Nothing of the input in the sentence — the exception being replaced
        # quotes the bytes it choked on, and those are part of the secret.
        raise ValueError(
            "the value on stdin is not valid UTF-8 text. ksecret stores text; "
            "encode a binary secret (base64, say) before writing it."
        ) from None


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def run(
    ctx: typer.Context,
    env_file: list[Path] = typer.Option(
        [], "--env-file", help="File of KEY=<reference> lines (repeatable)"
    ),
) -> None:
    """Run a command with every reference resolved into its environment."""
    command = list(ctx.args)
    if not command:
        typer.echo("ksecret run: no command given (use -- before it).", err=True)
        raise typer.Exit(2)

    try:
        entries = _collect(env_file)
    except OSError as exc:
        typer.echo(f"ksecret run: {exc.strerror}: {exc.filename}", err=True)
        raise typer.Exit(1) from None

    context = context_for(entries)
    environ = dict(context.env)
    resolved, errors = resolve_all(_references(entries), context)
    if errors:
        for error in errors:
            typer.echo(error.message, err=True)
        raise typer.Exit(1)
    environ.update(resolved)

    try:
        # Only the names this run declared carry the UTF-8 promise. Everything
        # else in `environ` was inherited from this process, and re-spelling it
        # breaks the child: a PATH directory named with the byte E9 is not found
        # by a child sent looking for C3 A9.
        completed = subprocess.run(
            command, env=encode_env(environ, utf8_keys=entries.keys())
        )
    except EnvironmentEncodingError as exc:
        typer.echo(f"ksecret run: {exc}", err=True)
        raise typer.Exit(1) from None
    except OSError as exc:
        typer.echo(
            f"ksecret run: cannot execute {command[0]}: {exc.strerror}", err=True
        )
        raise typer.Exit(127) from None
    raise typer.Exit(completed.returncode)


@app.command()
def check(
    refs: list[str] = typer.Argument(None, help="References to check"),
    env_file: list[Path] = typer.Option(
        [], "--env-file", help="File of KEY=<reference> lines (repeatable)"
    ),
    infra: bool = typer.Option(
        False,
        "--infra",
        help="Also check the sandbox secrets of the project in the current directory",
    ),
) -> None:
    """Report which references resolve — statuses only, never values."""
    try:
        entries = _collect(env_file)
    except OSError as exc:
        typer.echo(f"ksecret check: {exc.strerror}: {exc.filename}", err=True)
        raise typer.Exit(1) from None


    context = context_for(entries)

    results = [check_ref(key, ref, context) for key, ref in entries.items()]
    results += [check_ref(_label(ref), ref, context) for ref in refs or []]
    if infra:
        results += _check_infra()

    if not results:
        # A green that means "nothing was checked" is worse than no answer. It
        # is reachable three ways: no arguments, an --env-file holding only
        # comments, and a project whose [sandbox.secrets] is absent or empty.
        detail = (
            "the project declares no sandbox secrets"
            if infra
            else "name a reference, or pass --env-file / --infra"
        )
        typer.echo(f"ksecret check: nothing to check \u2014 {detail}.", err=True)
        raise typer.Exit(2)

    for result in results:
        _emit(f"{result.format()}\n")
    raise typer.Exit(1 if any(r.status == ERROR for r in results) else 0)


def _check_infra() -> list[CheckResult]:
    """Classify the project's sandbox secrets the way kinfra resolves them."""
    project_root = find_project_root()
    if project_root is None:
        typer.echo("ksecret check: no .devops-ai/ directory found.", err=True)
        raise typer.Exit(1)
    config = load_config(project_root)
    if config is None:
        typer.echo("ksecret check: no infra.toml in .devops-ai/.", err=True)
        raise typer.Exit(1)

    # Gitignored files live in the main checkout, not in a worktree cut from it,
    # and a declared literal is visible to a sibling reference — both are how
    # kinfra resolves these, which is the whole promise of --infra.
    base_dir = main_repo_root(project_root)
    if base_dir is None:
        # kinfra refuses here rather than guessing a root (sandbox_cmd), so
        # answering from a different base would be a confident wrong answer
        # about relative references — the failure this flag keeps having.
        typer.echo(
            "ksecret check: cannot determine main repository root.", err=True
        )
        raise typer.Exit(1)
    context = context_for(config.secrets, base_dir)
    return [
        check_ref(key, config.secrets[key], context)
        for key in sorted(config.secrets)
    ]


def _emit(text: str) -> None:
    """Write to stdout as UTF-8, whatever the locale claims.

    `ksecret` runs where the locale is often C — containers, cron, CI — and a
    secret is bytes, not text in the operator's codec. Going through stdout's
    own encoder raises `UnicodeEncodeError` there on a non-ASCII value, and on
    the em dash in a `check` line.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:  # a captured stream with no byte layer
        sys.stdout.write(text)
        return
    buffer.write(text.encode("utf-8"))
    buffer.flush()


def _label(ref: str) -> str:
    """What a bare reference may be called in output.

    A reference given on the command line stands in for its own key — fine while
    it is a reference. A literal is not: it *is* its value, and
    `postgres://user:password@host/db` is exactly the kind of literal
    `[sandbox.secrets]` carries. Only `--print` may emit a value.
    """
    return ref if provider_for(ref) is not None else LITERAL_LABEL


def _collect(env_files: list[Path]) -> dict[str, str]:
    """Every KEY=value line of every file, in order; later files win."""
    entries: dict[str, str] = {}
    for path in env_files:
        entries.update(read_env_file(path))
    return entries


def _references(entries: dict[str, str]) -> dict[str, str]:
    """The lines a provider claims."""
    return {k: v for k, v in entries.items() if provider_for(v) is not None}


def main() -> None:
    app()


if __name__ == "__main__":
    main()
