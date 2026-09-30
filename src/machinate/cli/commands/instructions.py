import typer

from machinate.cli.execution import execute
from machinate.cli.models import InstructionsResult
from machinate.cli.options import OUTPUT_FORMAT

# Paste-ready agent guidance, kept as one literal so the `## Machinate` section of
# AGENTS.md can be regenerated from it (a test asserts they match).
_INSTRUCTIONS = """\
## Machinate

Plans, tasks, context, and docs are plain Markdown files with YAML frontmatter
under `.machi/` — no server, no database. This project is planned with
machinate; regenerate this section with `machi instructions`.

### Targeting

- Pass `-p NAME` to plan-scoped commands (plan, task, context); doc commands are
  project-wide and take no plan. Without `-p` the current plan is used; select one
  with `machi plan select NAME` (humans only) and clear it with `plan unselect`.
- `MACHI_AI_AGENT` (alias `AI_AGENT`) names the agent in use. In agent mode `-p`
  is required, `plan select`/`unselect` fail, and output defaults to JSON. The
  first variable present decides; an empty value means human mode. `--format` and
  `MACHI_FORMAT` still override.
- `-P DIR` targets an exact project directory; otherwise the nearest `.machi/` is
  found by walking upward.

### Finding work

`machi search QUERY` searches every plan and all docs at once (narrow with `-p`)
and understands the store layout — use it instead of `ls`/`grep`/`rg` over
`.machi/`. Queries support fuzzy terms, `"phrases"`, and boolean/field syntax;
`machi search --help` documents the full grammar. Results are paths only.

### JSON output

JSON is the agent interface; read fields with `jq`:

    machi task list -p v2 --status todo | jq -r '.tasks[].name'
    machi plan info -p v2 | jq '.overview.tasks_by_status'
    machi info | jq '.overview | {plan_count, doc_count, tasks_by_status}'

Errors are JSON too and carry a machine-readable `code`. `machi schema <command>`
documents each result's shape. The one exception: get a bare editing path with
`machi <resource> path … --format text`.

### Reading and writing

- `machi plan|task|context|doc path` prints the absolute path
  (`plans/<plan>/tasks/<task>.md`) — edit bodies with your own file tools.
- Frontmatter is owned by machinate: edit bodies directly, change metadata through
  `machi … update` (`--summary`, `--tag` replaces the set, `--clear-tags` empties
  it, `--status` where the resource has one).
- Number tasks so they sort in order: `machi task add 01-login 02-logout`.
- Times: `created_at` is recorded in frontmatter (stable across copies),
  `modified_at` is the file mtime (body edits in any editor; copies and checkouts
  reset it), and plans also carry `last_activity_at` (newest `modified_at` across
  the plan's file, tasks, and context).
- `machi info` shows the project overview; `info` subcommands show metadata
  without the body.

### Commands

```text
machi init | info | search | instructions | schema
machi plan    add, list, show, info, path, select, unselect, update
machi task    add, list, show, info, path, update
machi context add, list, show, info, path, update
machi doc     add, list, show, info, path, update
```

`list` takes repeatable `--tag` (and `--status` for plans and tasks),
`--sort name|created_at|modified_at` (plans also `last_activity_at`),
`--descending`, `--limit`, and `--group`/`--no-group` (plans and tasks). Plan
statuses are `draft|active|done`; task statuses are `todo|in-progress|done`.
"""


def instructions_command(
    ctx: typer.Context,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print a paste-ready description of the machinate CLI for agent instruction files."""
    with execute(ctx, output_format) as run:
        run.emit(InstructionsResult(command="instructions", text=_INSTRUCTIONS))
