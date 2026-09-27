from pathlib import Path
from typing import Annotated

import typer

from machinate.cli.commands.selection import PlanSelectionError, resolve_plan_name
from machinate.cli.execution import execute
from machinate.cli.models import PathResult

_PLAN = Annotated[
    str | None,
    typer.Option("--plan", "-p", help="Plan to target; defaults to the current plan."),
]
_PROJECT = Annotated[
    Path | None,
    typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
]
_OUTPUT_FORMAT = Annotated[
    str | None, typer.Option("--format", help="Formatter name (text or json by default).")
]


def plan_path(
    context: typer.Context,
    plan: _PLAN = None,
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute editing path of a plan document."""
    with execute(context, "plan path", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        scope = project_context.project
        plan_name = resolve_plan_name(
            project_context.plans, plan, automation=run.settings.automation
        )
        target = scope.storage / project_context.plans.path(plan_name)
        result = PathResult(
            command="plan path",
            project=scope,
            plan=plan_name,
            path=target,
            kind="plan",
            exists=target.is_file(),
        )
        run.render(result)


def task_path(
    context: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Task name; omit to print the plan's tasks directory."),
    ] = None,
    plan: _PLAN = None,
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a task document or the tasks directory."""
    with execute(context, "task path", output_format, PlanSelectionError) as run:
        task_name = name
        project_context = run.prepare(project)
        scope = project_context.project
        plan_name = resolve_plan_name(
            project_context.plans, plan, automation=run.settings.automation
        )
        if task_name is None:
            target = scope.storage / project_context.tasks.directory(plan_name)
            result = PathResult(
                command="task path",
                project=scope,
                plan=plan_name,
                path=target,
                kind="tasks_directory",
                exists=target.is_dir(),
            )
        else:
            target = scope.storage / project_context.tasks.path(plan_name, task_name)
            result = PathResult(
                command="task path",
                project=scope,
                plan=plan_name,
                path=target,
                kind="task",
                exists=target.is_file(),
            )
        run.render(result)


def context_path(
    context: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Context name; omit to print the plan's context directory."),
    ] = None,
    plan: _PLAN = None,
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a context document or the context directory."""
    with execute(context, "context path", output_format, PlanSelectionError) as run:
        context_name = name
        project_context = run.prepare(project)
        scope = project_context.project
        plan_name = resolve_plan_name(
            project_context.plans, plan, automation=run.settings.automation
        )
        if context_name is None:
            target = scope.storage / project_context.contexts.directory(plan_name)
            result = PathResult(
                command="context path",
                project=scope,
                plan=plan_name,
                path=target,
                kind="context_directory",
                exists=target.is_dir(),
            )
        else:
            target = scope.storage / project_context.contexts.path(plan_name, context_name)
            result = PathResult(
                command="context path",
                project=scope,
                plan=plan_name,
                path=target,
                kind="context",
                exists=target.is_file(),
            )
        run.render(result)
