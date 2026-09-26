# machinate

File-based project planning for coding agents. Plans, tasks, and context live as plain
Markdown under a real `.machi/` directory — no server, no database.

## Install

```bash
uv tool install git+https://github.com/eelcovdw/machinate.git
```

## Quick start

```bash
machi init                       # initialize a project in the current directory
machi plan add auth              # create a plan (does not change selection)
machi plan set auth              # make it the current plan
machi task add login logout      # add tasks
machi context add spec           # add context documents
machi plan show                  # show the current plan
```

## Commands

Options go **after** the command. `-p/--plan` selects an existing plan; without it the
current plan is used. `-P/--project` targets an exact project directory; otherwise
machinate discovers the nearest `.machi/` by walking upward.

```bash
machi init [-P DIR] [--project-name NAME]      # initialize a project (default: cwd)
machi info [-p PLAN] [-P DIR]                  # project overview, or a plan with -p

machi plan add <name> [--summary] [--status] [--tag]
machi plan list [--status] [--tag] [--search] [--sort]
machi plan show [-p PLAN]                      # default: current plan
machi plan set <name>
machi plan update [-p PLAN] [--status] [--summary] [--tag]
machi plan info [-p PLAN]
machi plan path [-p PLAN]

machi task add <name...> [-p PLAN]
machi task list [-p PLAN]
machi task show <name> [-p PLAN]
machi task update <name> [-p PLAN] [--status] [--summary] [--tag]
machi task info <name> [-p PLAN]
machi task path [<name>] [-p PLAN]

machi context add <name...> [-p PLAN]
machi context list [-p PLAN]
machi context show <name> [-p PLAN]
machi context update <name> [-p PLAN] [--summary] [--tag]
machi context info <name> [-p PLAN]
machi context path [<name>] [-p PLAN]

machi schema [COMMAND]                         # JSON Schema for command results
machi instructions                             # paste-ready agent usage block
```

`machi list` is a hidden alias for `machi plan list`. List commands accept filters
such as `--status`, `--tag`, `--search`, and `--sort`; run `machi <group> <command> --help`
for the full set.

## Output

Every command supports `--format text|json`. Precedence is `--format` > `MACHI_FORMAT`
> default (text, or json in non-interactive mode). `machi schema` describes the exact
JSON shape of each command's result.

## Layout

```
.machi/
  machinate.toml        # project state (name, current plan)
  {plan}/
    plan.md             # plan document
    tasks/*.md          # task documents
    context/*.md        # context documents
```

## Development

machinate targets Python 3.14 and uses [`uv`](https://docs.astral.sh/uv/). The
`machi` and `machinate` entry points are installed editable, so source changes are
picked up immediately.

```bash
uv sync                  # install dependencies
uv run pytest            # run the test suite
uv run ruff check        # lint
uv run ruff format       # format
uv run basedpyright      # type check
```
