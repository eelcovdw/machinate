from pathlib import Path
from typing import Annotated

import typer

from machinate.console import get_console, print_files_with_summary, short_path
from machinate.plan_service import get_plans_dir
from machinate.settings import Settings
from machinate.task_service import add_task, list_tasks, resolve_task_file, set_task_status
from machinate.templating import TASK_STATUS_ORDER, TaskStatus, parse_frontmatter

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
    console = get_console(Settings())
    if filenames:
        for filename in filenames:
            path = add_task(plans_dir, plan, filename)
            console.print(short_path(path))
    else:
        path = add_task(plans_dir, plan)
        console.print(short_path(path))


@task_app.command(name="status")
def task_status(
    task: Annotated[str, typer.Argument(help="Task prefix (e.g. '01').")],
    new_status: Annotated[
        TaskStatus | None,
        typer.Argument(help="New status: todo, in-progress, done. Omit to print current status."),
    ] = None,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan name. Defaults to current plan."),
    ] = None,
) -> None:
    """Print or set a task's status."""
    plans_dir = get_plans_dir()
    if new_status is not None:
        set_task_status(plans_dir, task, new_status, plan)
    path = resolve_task_file(plans_dir, task, plan)
    meta, _ = parse_frontmatter(path.read_text())
    console = get_console(Settings())
    console.print(meta.get("status", "unknown"))


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
    by_status: dict[str, list[Path]] = {}
    for f in files:
        meta, _ = parse_frontmatter(f.read_text())
        status = meta.get("status", "unknown")
        by_status.setdefault(status, []).append(f)
    console = get_console(Settings())
    ordered = [s for s in TASK_STATUS_ORDER if s in by_status]
    ordered += [s for s in by_status if s not in ordered]
    for status in ordered:
        console.print(f"[muted]{status}[/muted]")
        print_files_with_summary(console, by_status[status], indent=1)
