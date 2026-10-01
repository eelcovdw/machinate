# machinate

A lightweight CLI to plan work with coding agents. It reads and writes a `.machi/` directory in
your project, which holds four kinds of plain Markdown documents:

- plans: units of work with a goal and a status (`draft` / `active` / `done`)
- tasks: the concrete steps that make up a plan
- context: background documents an agent needs while working
- docs: project-level reference material shared across plans

One state file (`.machi/machinate.toml`) records project settings and the current
plan. There is no server or database: documents stay editable by hand, and search
(`machi search`) runs locally through [Tantivy](https://github.com/quickwit-oss/tantivy).

## Install

```bash
uv tool install machinate   # or: pipx install machinate
```

Requires Python 3.14.

## Usage

```bash
machi init                         # create .machi/ in this project
machi plan add auth                # create a plan
machi plan select auth             # make it the current plan
machi task add 01-login 02-logout  # create two tasks on the current plan
machi task list                    # show the tasks
machi context add spec             # add a plan context document
machi doc add architecture         # add a project-level doc
machi plan show auth               # show the full plan
```

That leaves this tree on disk:

```text
.machi/
├── machinate.toml             project name and the selected plan
├── docs/
│   └── architecture.md        machi doc add architecture
└── plans/
    └── auth/
        ├── plan.md            machi plan add auth
        ├── tasks/
        │   ├── 01-login.md    machi task add 01-login 02-logout
        │   └── 02-logout.md
        └── context/
            └── spec.md        machi context add spec
```

Every document is Markdown with YAML frontmatter, so it stays diffable and editable by
hand. `machi plan select` only rewrites `machinate.toml`; each `add` command creates one
file, and task and context names may contain subdirectories to nest documents.

`machi search` searches every plan and all docs through Tantivy, with fuzzy and prefix
matching on by default:

- `machi search "login OR logout"` searches all plans and docs.
- `machi search '"bearer token"' -p auth` matches a phrase in one plan.
- `machi search -p auth --glob 'tasks/**/*.md'` filters by path, ANDed with the query.

Plan commands take the plan name positionally (`machi plan show auth`). `-p PLAN`
narrows tasks, context, or search to one plan; `-P PROJECT_DIR` a project, `--format json`
for agents.

### One store for several repos

Point a repo at an existing store instead of creating its own:

```bash
machi init --redirect ../planning   # run in repo/; ../planning holds the shared store
```

That writes only a redirect, `repo/.machi/machinate.toml`:

```toml
project_dir = "../planning"
```

Absolute and `~` paths are stored as given; relative paths are stored relative to the
repo.

`MACHI_PROJECT_DIR` names the project directory like `-P`; `-P` wins, then the env
var, then upward discovery. `machi init` ignores it, so an env pointing at the
shared store can't retarget init. Every repo using the store shares one
`plan select`, so a selection made in one repo applies to the others.

## Use with coding agents

Add the agent instructions to your project, so agents know how to use machinate:

```bash
machi instructions >> AGENTS.md
```

When `AI_AGENT` (set by Claude Code and other agents that follow that convention) or
`MACHI_AI_AGENT` is set, machinate runs in agent mode: plan-scoped commands need an
explicit plan, `plan select` is disabled so parallel sessions can't retarget each other,
and output defaults to JSON. Errors carry a machine-readable `code`, and
`machi schema <command>` prints the JSON shape of each result.

## Development

See [CONTRIBUTING.md](https://github.com/eelcovdw/machinate/blob/main/CONTRIBUTING.md) for setup, checks, and releasing.
