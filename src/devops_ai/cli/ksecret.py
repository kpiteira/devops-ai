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

from devops_ai.config import find_project_root, load_config
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
from devops_ai.worktree import main_repo_root

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
    environ.update(_literals(entries))
    resolved, errors = resolve_all(
        _references(entries), ResolveContext(env=environ)
    )
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

    environ = dict(os.environ)
    environ.update(_literals(entries))
    context = ResolveContext(env=environ)

    results = [check_ref(key, ref, context) for key, ref in entries.items()]
    results += [check_ref(ref, ref, context) for ref in refs or []]
    if infra:
        results += _check_infra()

    for result in results:
        sys.stdout.write(f"{result.format()}\n")
    raise typer.Exit(1 if any(r.status == ERROR for r in results) else 0)


def _check_infra() -> list[CheckResult]:
    """Classify [sandbox.secrets] exactly as `kinfra impl` would resolve it."""
    project_root = find_project_root()
    if project_root is None:
        typer.echo("ksecret check: no .devops-ai/ directory found.", err=True)
        raise typer.Exit(1)
    config = load_config(project_root)
    if config is None:
        typer.echo("ksecret check: no infra.toml in .devops-ai/.", err=True)
        raise typer.Exit(1)

    # Gitignored files live in the main checkout, not in a worktree cut from it.
    base_dir = main_repo_root(project_root) or project_root
    context = ResolveContext(base_dir=base_dir)
    return [
        check_ref(key, config.secrets[key], context)
        for key in sorted(config.secrets)
    ]


def _collect(env_files: list[Path]) -> dict[str, str]:
    """Every KEY=value line of every file, in order; later files win."""
    entries: dict[str, str] = {}
    for path in env_files:
        entries.update(read_env_file(path))
    return entries


def _literals(entries: dict[str, str]) -> dict[str, str]:
    """The lines no provider claims.

    They land in the environment before resolution and override the parent's,
    so a reference can name a variable declared beside it (`OP_ACCOUNT=` in
    agent-memory's env file) and the provider it feeds will see it.
    """
    return {k: v for k, v in entries.items() if provider_for(v) is None}


def _references(entries: dict[str, str]) -> dict[str, str]:
    """The lines a provider claims."""
    return {k: v for k, v in entries.items() if provider_for(v) is not None}


def main() -> None:
    app()


if __name__ == "__main__":
    main()
