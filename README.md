# machinate

File-based project planning for coding agents. Plans, tasks, and context as plain
Markdown in `.machi/`.

## Overview

A **project** is a directory with a `.machi/` store. Within it:

- **plans** — units of work with a goal and a status (`draft` / `active` / `done`)
- **tasks** — the concrete steps that make up a plan
- **context** — background documents an agent needs while working

Everything is plain Markdown with YAML frontmatter: diffable, greppable, and editable
by hand, while the CLI provides structure and tracks things like the current plan.

## Install

```bash
uv tool install git+https://github.com/eelcovdw/machinate.git
```

## Usage

```bash
machi init                   # initialize a project
machi plan add auth          # create a plan
machi plan set auth          # select it as current active plan
machi task add login logout  # add tasks on the active plan
machi task list              # list all tasks on the active plan
machi context add spec       # add context
machi plan show              # read the current plan
machi plan info              # progress overview
machi plan list              # list all plans
```

`-p PLAN` targets a plan, `-P PROJECT_DIR` a project, `--format json` for agents.

## Development

Python 3.14 + [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync && uv run pytest
uv run ruff check && uv run ruff format
uv run basedpyright
```
