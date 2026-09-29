import typer

from machinate.cli.execution import execute
from machinate.cli.models import InstructionsResult
from machinate.cli.options import OUTPUT_FORMAT

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
- Number tasks so they sort in the intended order: `machi task add 01-login 02-logout`.
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

`list` subcommands take repeatable `--tag`/`--status`, `--sort
name|created|updated`, `--descending`, `--limit`, and `--no-group` to drop
status grouping. Plan statuses are `draft|active|done`; task statuses are
`todo|in-progress|done`.
"""


def instructions_command(
    context: typer.Context,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print a paste-ready description of the machinate CLI for agent instruction files."""
    with execute(context, output_format) as run:
        run.render(InstructionsResult(command="instructions", text=_INSTRUCTIONS))
