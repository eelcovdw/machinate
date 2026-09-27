# machinate

A lightweight CLI to plan work with coding agents. It reads and writes a `.machi/` directory in
your project, which holds three kinds of plain Markdown documents:

- plans: units of work with a goal and a status (`draft` / `active` / `done`)
- tasks: the concrete steps that make up a plan
- context: background documents an agent needs while working

One state file (`.machi/machinate.toml`) records project settings and the current
plan. There is no server or database: documents stay editable by hand, and search
(`machi find`) runs locally through Tantivy.

## Install

```bash
uv tool install git+https://github.com/eelcovdw/machinate.git
```

## Usage

```bash
machi init                         # create .machi/ in this project
machi plan add auth                # create a plan
machi plan select auth             # make it the current plan
machi task add 01-login 02-logout  # create two tasks on the current plan
machi task list                    # show the tasks
machi context add spec             # add a context document
machi plan show                    # show the full plan
```

That leaves this tree on disk:

```text
.machi/
├── machinate.toml             project name and the selected plan
└── plans/
    └── auth/
        ├── plan.md            machi plan add auth
        ├── tasks/
        │   ├── 01-login.md    machi task add login logout
        │   └── 02-logout.md
        └── context/
            └── spec.md        machi context add spec
```

Every document is Markdown with YAML frontmatter, so it stays diffable and editable by
hand. `machi plan select` only rewrites `machinate.toml`; each `add` command creates one
file, and task and context names may contain subdirectories to nest documents.

`machi find` searches every plan through Tantivy, with fuzzy and prefix matching on by
default:

- `machi find "login OR logout"` searches all plans.
- `machi find '"bearer token"' --plan auth` matches a phrase in one plan.
- `machi find --plan auth --glob 'tasks/**/*.md'` filters by path, ANDed with the query.

`-p PLAN` targets a plan, `-P PROJECT_DIR` a project, `--format json` for agents.

## Development

Python 3.14 and [`uv`](https://docs.astral.sh/uv/). A Makefile wraps the usual
commands:

```bash
make setup   # uv sync
make lint    # ruff check, ruff format --check, basedpyright
make test    # pytest
```
