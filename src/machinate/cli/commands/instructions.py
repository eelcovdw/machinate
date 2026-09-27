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

machinate keeps a project's plans, tasks, and context as plain Markdown with YAML
frontmatter under `.machi/` — no server, no database. This project is planned
with it, and `machi instructions` prints a paste-ready CLI overview for agent
instruction files.

### Finding work

`machi find QUERY` searches every plan at once (unless scoped with `-p`) and
understands the store layout — use it instead of `ls`/`grep`/`rg` over `.machi/`.

```bash
machi find atomic-state-writes                       # across all plans
machi find "atomic state" -p review-storage-fixes   # scope to one plan
machi find 'body:"truncates machinate.toml"'         # phrase in the body field
machi find --glob 'tasks/*.md'                       # list by glob, no query
```

Results list matching paths (`plans/<plan>/tasks/<task>.md`).
The query language supports fuzzy terms, `"phrases"`, `field:term` (`path:`/
`body:`), `+`/`-`, `AND`/`OR`/`NOT`, and ranges — see `machi find --help` for
the full grammar and output options.

### Targeting

- `-p NAME` targets a plan; without it, the current plan is used. **If no
  current plan is set, plan-scoped commands fail with `No current plan is
  selected` — pass `-p` explicitly.** Select a current plan with
  `machi plan select NAME`; clear it with `machi plan unselect`.
- Automation mode (`MACHI_AUTOMATION=true`) always requires `-p` and defaults
  output to JSON.
- `-P DIR` targets an exact project directory; otherwise machinate discovers
  the nearest `.machi/` by walking upward.

### Reading and writing

- Every command takes `--format text|json`. Precedence: `--format` >
  `MACHI_FORMAT` > default (text, or json in automation mode).
  `machi schema <command>` documents the exact JSON shape of results.
- `machi plan path`, `machi task path NAME`, and `machi context path NAME` print
  absolute editing paths — edit bodies with your own file tools. With no name
  they print the containing directory.
- Change status, tags, and summaries with `machi plan|task|context update`,
  e.g. `machi task update NAME --status in-progress --tag x`. `--tag` replaces
  the tag set; `--summary ''` clears the summary.
- `machi plan|task|context info` shows metadata without the body; `machi info`
  shows the project overview.

### Commands

```text
machi init | info | find | instructions | schema
machi plan    add, list, show, info, path, set, update
machi task    add, list, show, info, path, update
machi context add, list, show, info, path, update
```

`list` subcommands accept `--search`, `--search-body`, repeatable `--tag` and
`--status`, `--sort name|created|updated`, `--descending`, and `--limit`.
`plan list` and `task list` group rows under status headers by default; pass
`--no-group-by` to keep the sort order.
Plan statuses are `draft|active|done`; task statuses are `todo|in-progress|done`.
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
