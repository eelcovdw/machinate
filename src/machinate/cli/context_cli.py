from typing import Annotated

import typer

from machinate.console import short_path
from machinate.context_service import add_context, list_context
from machinate.plan_service import get_plans_dir

context_app = typer.Typer(
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)


@context_app.command(name="add")
def context_add(
    filenames: Annotated[
        list[str] | None,
        typer.Argument(help="Context filename(s)."),
    ] = None,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan name. Defaults to current plan."),
    ] = None,
) -> None:
    """Ensure context/ dir exists and print the path. Pipe-friendly."""
    plans_dir = get_plans_dir()
    if filenames:
        for filename in filenames:
            path = add_context(plans_dir, plan, filename)
            print(short_path(path))  # noqa: T201
    else:
        path = add_context(plans_dir, plan)
        print(short_path(path))  # noqa: T201


@context_app.command(name="list")
def context_list(
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan name. Defaults to current plan."),
    ] = None,
) -> None:
    """List context files for a plan."""
    plans_dir = get_plans_dir()
    files = list_context(plans_dir, plan)
    for f in files:
        print(short_path(f))  # noqa: T201
