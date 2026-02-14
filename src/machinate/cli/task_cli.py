from typing import Annotated

import typer

from machinate.console import get_console, short_path
from machinate.plan_service import get_plans_dir
from machinate.settings import Settings
from machinate.task_service import add_task, list_tasks
from machinate.templating import parse_frontmatter

task_app = typer.Typer(
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)


@task_app.command(name="add")
def task_add(
    filenames: Annotated[
        list[str] | None,
        typer.Argument(help="Task filename(s)."),
    ] = None,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan name. Defaults to current plan."),
    ] = None,
) -> None:
    """Ensure tasks/ dir exists and print the path. Pipe-friendly."""
    plans_dir = get_plans_dir()
    if filenames:
        for filename in filenames:
            path = add_task(plans_dir, plan, filename)
            print(short_path(path))  # noqa: T201
    else:
        path = add_task(plans_dir, plan)
        print(short_path(path))  # noqa: T201


@task_app.command(name="list")
def task_list(
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan name. Defaults to current plan."),
    ] = None,
) -> None:
    """List task files for a plan."""
    plans_dir = get_plans_dir()
    files = list_tasks(plans_dir, plan)
    by_status: dict[str, list[str]] = {}
    for f in files:
        meta, _ = parse_frontmatter(f.read_text())
        status = meta.get("status", "unknown")
        by_status.setdefault(status, []).append(short_path(f))
    console = get_console(Settings())
    for status, paths in by_status.items():
        console.print(f"[muted]{status}[/muted]")
        for p in paths:
            console.print(f"  [path]{p}[/path]")
