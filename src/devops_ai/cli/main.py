"""kinfra CLI — Developer infrastructure for worktree and sandbox management."""

import typer

from devops_ai.cli.done import done_command
from devops_ai.cli.impl import impl_command
from devops_ai.cli.init_cmd import init_command
from devops_ai.cli.observability import _down_command, _status_command, _up_command
from devops_ai.cli.spec import spec_command
from devops_ai.cli.status import status_command
from devops_ai.cli.worktrees import worktrees_command

app = typer.Typer(
    name="kinfra",
    help="Developer infrastructure CLI for worktree and sandbox management.",
    no_args_is_help=True,
)

observability_app = typer.Typer(
    help="Manage shared observability stack (Jaeger, Grafana, Prometheus).",
    no_args_is_help=True,
)
app.add_typer(observability_app, name="observability")


@app.command()
def init() -> None:
    """Initialize kinfra for the current project."""
    code = init_command()
    raise typer.Exit(code)


@app.command()
def spec(feature: str = typer.Argument(help="Feature name")) -> None:
    """Create a spec (design) worktree for a feature."""
    code = spec_command(feature)
    raise typer.Exit(code)


@app.command()
def done(
    name: str = typer.Argument(help="Worktree name or partial match"),
    force: bool = typer.Option(
        False, "--force", help="Remove even if dirty"
    ),
) -> None:
    """Remove a worktree (with dirty check)."""
    code, msg = done_command(name, force=force)
    typer.echo(msg)
    raise typer.Exit(code)


@app.command()
def worktrees() -> None:
    """List all active worktrees."""
    code = worktrees_command()
    raise typer.Exit(code)


@app.command(name="impl")
def impl_cmd(
    feature_milestone: str = typer.Argument(
        help="Feature/milestone (e.g., my-feature/M1)"
    ),
    session: bool = typer.Option(
        False,
        "--session",
        help="Create an agent-deck session with Claude",
    ),
) -> None:
    """Create an implementation worktree with sandbox."""
    code, msg = impl_command(feature_milestone, session=session)
    typer.echo(msg)
    raise typer.Exit(code)


@app.command()
def status() -> None:
    """Show sandbox details for current directory."""
    code, msg = status_command()
    typer.echo(msg)
    raise typer.Exit(code)


@observability_app.command(name="up")
def obs_up() -> None:
    """Start the shared observability stack."""
    code, msg = _up_command()
    typer.echo(msg)
    raise typer.Exit(code)


@observability_app.command(name="down")
def obs_down() -> None:
    """Stop the shared observability stack."""
    code, msg = _down_command()
    typer.echo(msg)
    raise typer.Exit(code)


@observability_app.command(name="status")
def obs_status() -> None:
    """Show observability stack status."""
    code, msg = _status_command()
    typer.echo(msg)
    raise typer.Exit(code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
