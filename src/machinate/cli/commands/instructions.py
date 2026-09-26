from typing import Annotated

import typer
from pydantic import ValidationError

from machinate.cli.dependencies import get_dependencies
from machinate.cli.errors import describe_error
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import ErrorResult, InstructionsResult
from machinate.cli.settings import Settings

# Paste-ready agent guidance. Kept as one literal so it is copied verbatim into a
# project's instruction file; `test_instructions_lists_every_registered_command`
# fails if a registered command is missing here.
_INSTRUCTIONS = """\
## Machinate

machinate is a file-based planning tool for coding agents. It keeps a project's
plans, tasks, and context as plain Markdown with TOML frontmatter under `.machi/`,
with no server or database, and this project is planned with it.

Prefer the `machi` CLI over `ls`/`find`/`Glob` — it returns structured output and
keeps links consistent.

### Commands

```text
machi init          Initialize a project directory.
machi info          Show a project or plan overview.
machi instructions  Print this block.
machi schema        Print the JSON Schema for command results.
machi plan          add, list, show, info, path, set, update
machi task          add, list, show, info, path, update
machi context       add, list, show, info, path, update
```

### Targeting

- Target an existing plan with `-p NAME`; without it the current plan is used.
- Non-interactive mode (`MACHI_INTERACTIVE=false`) requires `-p`.
- `-P DIR` targets an exact project directory; otherwise machinate discovers the
  nearest `.machi/` by walking upward.

### Output

- Use `--format text|json`. Precedence: `--format` > `MACHI_FORMAT` > default
  (text, or json in non-interactive mode).
- `machi schema` documents the exact JSON shape of every command result.

### Editing

- `machi plan path`, `machi task path NAME`, and `machi context path NAME` print
  absolute editing paths; edit bodies with your own file tools.
- Change status, tags, and summaries with `machi plan|task|context update`."""


def build_instructions() -> str:
    """Return the paste-ready description of the machinate CLI."""
    return _INSTRUCTIONS


def instructions_command(
    context: typer.Context,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Print a paste-ready description of the machinate CLI for agent instruction files."""
    dependencies = get_dependencies(context)
    formatter = Formatter()
    try:
        settings = Settings()
        name = output_format or settings.format
        formatter = select_formatter(name, dependencies.formatters)
        result = InstructionsResult(text=build_instructions())
    except (UnknownFormatError, ValidationError) as exc:
        typer.echo(
            formatter.format(ErrorResult(command="instructions", error=describe_error(exc))),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))
