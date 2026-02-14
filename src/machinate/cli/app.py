from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.prompt import Confirm

from machinate.cli.context_cli import context_app
from machinate.cli.task_cli import task_app
from machinate.console import get_console, short_path
from machinate.plan_service import (
    create_plan,
    execute_init,
    get_current_plan,
    get_plans_dir,
    list_plans,
    plan_init,
    set_plan,
    show_plan,
)
from machinate.settings import Settings
from machinate.templating import parse_frontmatter

app = typer.Typer(
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)
app.add_typer(context_app, name="context")
app.add_typer(task_app, name="task")


@app.command()
def init(
    plans_dir: Annotated[
        Path | None,
        typer.Option(help="Explicit plans directory."),
    ] = None,
    project_name: Annotated[
        str | None,
        typer.Option(help="Project name. Defaults to MACHINATE_PROJECT or dir name."),
    ] = None,
    override: Annotated[
        bool,
        typer.Option("--override", help="Override existing state and symlink."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt."),
    ] = False,
) -> None:
    """Initialize a machinate project."""
    if plans_dir and project_name:
        msg = "--plans-dir and --project-name are mutually exclusive."
        raise typer.BadParameter(msg)
    settings = Settings()
    console = get_console(settings)
    plan = plan_init(
        settings=settings,
        plans_dir=plans_dir,
        project_name=project_name,
    )

    console.print(f"[info]Plans directory:[/info] [path]{short_path(plan.plans_dir)}[/path]")
    if plan.symlink:
        console.print(
            f"[info]Symlink:[/info] [path]{short_path(plan.symlink)}[/path]"  # pyright: ignore[reportImplicitStringConcatenation]
            f" → [path]{short_path(plan.plans_dir)}[/path]"
        )

    if not yes and not Confirm.ask("Proceed?", console=console):
        raise typer.Abort

    execute_init(plan, override=override)
    console.print(
        f"[success]Initialized[/success] plans at [path]{short_path(plan.plans_dir)}[/path]"
    )
    if plan.symlink and plan.symlink.is_symlink():
        console.print(f"[info]Created symlink[/info] [path]{short_path(plan.symlink)}[/path]")


@app.command()
def new(
    name: str,
    current: Annotated[
        bool,
        typer.Option("--current/--no-current", help="Set as current plan."),
    ] = True,
    exist_ok: Annotated[
        bool,
        typer.Option("--exist-ok", help="Don't error if plan already exists."),
    ] = False,
) -> None:
    """Create a new plan."""
    plans_dir = get_plans_dir()
    plan_dir = create_plan(plans_dir, name, exist_ok=exist_ok)

    if current:
        set_plan(plans_dir, name)

    print(short_path(plan_dir / "plan.md"))  # noqa: T201


@app.command(name="list")
def list_cmd() -> None:
    """List all plans."""
    settings = Settings()
    console = get_console(settings)
    plans_dir = get_plans_dir()
    current = get_current_plan(plans_dir)
    names = list_plans(plans_dir)

    if not names:
        console.print("[muted]No plans yet. Run 'machi new <name>' to create one.[/muted]")
        return

    for name in names:
        marker = "▸ " if name == current else "  "
        plan_meta, _ = parse_frontmatter((plans_dir / name / "plan.md").read_text())
        plan_summary = plan_meta.get("summary", "")
        console.print(f"{marker}[name]{name}[/name]")
        if plan_summary:
            console.print(Padding(f"[muted]{plan_summary}[/muted]", (0, 0, 0, 4)))


@app.command(name="set")
def set_cmd(name: str) -> None:
    """Set the current plan."""
    settings = Settings()
    console = get_console(settings)
    plans_dir = get_plans_dir()
    set_plan(plans_dir, name)
    console.print(f"[success]Current plan:[/success] [name]{name}[/name]")


def _print_files_with_summary(console: Console, files: list[Path], indent: int) -> None:
    """Print file paths with optional summary from frontmatter."""
    for f in files:
        meta, _ = parse_frontmatter(f.read_text())
        summary = meta.get("summary", "")
        console.print(f"{'  ' * indent}[path]{short_path(f)}[/path]")
        if summary:
            console.print(Padding(f"[muted]{summary}[/muted]", (0, 0, 0, indent * 2 + 2)))


@app.command()
def show(
    name: Annotated[
        str | None,
        typer.Argument(help="Plan name. Defaults to current plan."),
    ] = None,
) -> None:
    """Show plan details."""
    settings = Settings()
    console = get_console(settings)
    plans_dir = get_plans_dir()
    info = show_plan(plans_dir, name)

    meta, body = parse_frontmatter(info.plan_content)

    console.print(f"[name]{info.name}[/name]")
    if meta:
        parts = [f"[muted]{k}:[/muted] {v}" for k, v in meta.items()]
        console.print("  ".join(parts))
    if info.task_files:
        console.print("\n[info]Tasks:[/info]")
        by_status: dict[str, list[Path]] = {}
        for f in info.task_files:
            task_meta, _ = parse_frontmatter(f.read_text())
            status = task_meta.get("status", "unknown")
            by_status.setdefault(status, []).append(f)
        for status, files in by_status.items():
            console.print(f"  [muted]{status}[/muted]")
            _print_files_with_summary(console, files, indent=2)
    if info.context_files:
        console.print("\n[info]Context:[/info]")
        _print_files_with_summary(console, info.context_files, indent=1)
    if body.strip():
        console.print()
        console.print(Markdown(body, justify="left"))
