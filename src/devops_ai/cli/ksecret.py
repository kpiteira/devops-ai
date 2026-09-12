"""ksecret CLI — resolve secret references, and run commands with them injected.

Three verbs, one resolver. `read` answers about a single reference and prints its
value only when asked to. `run` puts resolved values in a child's environment and
writes nothing to disk. `check` reports what resolves without ever showing a value.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

from devops_ai.secrets import (
    ERROR,
    CheckResult,
    ResolveContext,
    SecretResolutionError,
    provider_for,
    read_env_file,
    resolve,
    resolve_all,
)
from devops_ai.secrets import (
    check as check_ref,
)

app = typer.Typer(
    name="ksecret",
    help="Resolve secret references through pluggable providers.",
    no_args_is_help=True,
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
        sys.stdout.write(value if no_newline else f"{value}\n")
    else:
        sys.stdout.write(f"ok {ref}\n")
    raise typer.Exit(0)


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

    environ = dict(os.environ)
    refs = _apply_literals(entries, environ)
    resolved, errors = resolve_all(refs, ResolveContext(env=environ))
    if errors:
        for error in errors:
            typer.echo(error.message, err=True)
        raise typer.Exit(1)
    environ.update(resolved)

    completed = subprocess.run(command, env=environ)
    raise typer.Exit(completed.returncode)


@app.command()
def check(
    refs: list[str] = typer.Argument(None, help="References to check"),
    env_file: list[Path] = typer.Option(
        [], "--env-file", help="File of KEY=<reference> lines (repeatable)"
    ),
) -> None:
    """Report which references resolve — statuses only, never values."""
    try:
        entries = _collect(env_file)
    except OSError as exc:
        typer.echo(f"ksecret check: {exc.strerror}: {exc.filename}", err=True)
        raise typer.Exit(1) from None

    environ = dict(os.environ)
    pending = _apply_literals(entries, environ)
    context = ResolveContext(env=environ)

    results: list[CheckResult] = [
        CheckResult(key=key, status="literal")
        if key not in pending
        else check_ref(key, pending[key], context)
        for key in entries
    ]
    results.extend(check_ref(ref, ref, context) for ref in refs or [])

    for result in results:
        sys.stdout.write(f"{result.format()}\n")
    raise typer.Exit(1 if any(r.status == ERROR for r in results) else 0)


def _collect(env_files: list[Path]) -> dict[str, str]:
    """Every KEY=value line of every file, in order; later files win."""
    entries: dict[str, str] = {}
    for path in env_files:
        entries.update(read_env_file(path))
    return entries


def _apply_literals(
    entries: dict[str, str], environ: dict[str, str]
) -> dict[str, str]:
    """Put literal lines in the environment; return the ones needing resolution.

    Literals land first and override the parent environment, so a reference can
    name a variable declared beside it (`OP_ACCOUNT=` in agent-memory's env file).
    """
    refs: dict[str, str] = {}
    for key, value in entries.items():
        if provider_for(value) is None:
            environ[key] = value
        else:
            refs[key] = value
    return refs


def main() -> None:
    app()


if __name__ == "__main__":
    main()
