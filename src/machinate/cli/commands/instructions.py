from typing import Annotated

import typer
from pydantic import ValidationError

from machinate.cli.dependencies import get_dependencies
from machinate.cli.errors import describe_error
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import ErrorResult, InstructionsResult
from machinate.cli.settings import Settings

# Paste-ready agent guidance. Kept as one literal so it stays word-for-word in
# sync with the `## Machinate` section of this project's AGENTS.md.
_INSTRUCTIONS = """\
## Machinate

Plans, tasks, and context are plain Markdown files with YAML frontmatter under
`.machi/` — no server, no database. This project is planned with machinate;
regenerate this section with `machi instructions`.

### Finding work

`machi find QUERY` searches every plan at once (scope with `-p`) and understands
the store layout — use it instead of `ls`/`grep`/`rg` over `.machi/`. Queries
support fuzzy terms, `"phrases"`, and boolean/field syntax; `machi find --help`
documents the full grammar.

### Targeting

- `-p NAME` targets a plan; without it, the current plan is used. Select one with
  `machi plan select NAME`, clear it with `machi plan unselect`. With no current
  plan set, plan-scoped commands fail until `-p` is passed.
- `MACHI_AUTOMATION=true` requires `-p` and defaults output to JSON.
- `-P DIR` targets an exact project directory; otherwise the nearest `.machi/`
  is found by walking upward.

### Reading and writing

- Output is text or JSON — `--format` beats `MACHI_FORMAT`, which beats the
  mode default. `machi schema <command>` documents each result's JSON shape.
- `machi plan|task|context path` prints absolute editing paths
  (`plans/<plan>/tasks/<task>.md`) — edit bodies with your own file tools.
- `machi plan|task|context update` changes status, summary, or tags: `--tag`
  replaces the tag set, `--clear-tags` empties it.
- `machi info` shows the project overview; `info` subcommands show metadata
  without the body.

### Commands

```text
machi init | info | find | instructions | schema
machi plan    add, list, show, info, path, select, unselect, update
machi task    add, list, show, info, path, update
machi context add, list, show, info, path, update
```

`list` subcommands take `--search`, `--search-body`, repeatable `--tag`/
`--status`, `--sort name|created|updated`, `--descending`, `--limit`, and
`--no-group-by` to drop status grouping. Plan statuses are `draft|active|done`;
task statuses are `todo|in-progress|done`.
"""


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
