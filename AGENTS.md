# Machinate — Agent Instructions

File-based project planning CLI for Claude Code. Spec: @.claude/plans/spec-machinate.md
Design docs for the v2 rewrite live in `.dev-docs/` (`CLI.md` is the accepted CLI spec).

## Hard rules

- **Never commit or push.** Make changes in the working tree and stop for review. The user decides
  when and how anything is committed or pushed — do not run `git commit`, `git push`, or any
  history-rewriting command unless the user explicitly asks in the current turn.
- Do what the user asks. Simple requests like "create a file" or "add a function" do not need
  extensive investigation.
- Don't add placeholder/stub implementations unless asked to.
- Check diagnostics only when you're done with all edits to a file, not after every small change.
- Only change files directly related to the current task. Do not refactor or modify unrelated files.

## Working efficiently

- Locate work with `machi find QUERY` before any `ls`/`find`/plan enumeration.
- Answer a question with at most a couple of commands; do not audit.
- A question is not a work order. "What's next" means list the remaining tasks, not start them.
  Read files, run commands, or make edits only when the current request asks for it.
- A docs task is one gather and one edit — no read-backs and no live verification of text you
  just wrote from the real CLI.
- No live demo when the tests already cover the behavior.
- **Task status and tracking live on machinate tasks. Never maintain task lists or statuses
  inside a plan body (`plan.md`) — the plan is the spec, tasks are the tracker.**
- Stop when the request is satisfied. No post-completion bookkeeping (plan bodies, temp
  cleanup, status syncing) unless asked.
- Run everything through `uv` (`uv run machi …`, `uv run pytest`, …) — do not manually
  `source .venv/bin/activate`.

## Stack

- Python 3.14, uv, src layout (`src/machinate/`)
- CLI entry point: `machi` / `machinate` (installed editable); run via `uv run machi …`.
- CLI framework: `typer`
- Storage: a real `.machi/` directory per project, state in `.machi/machinate.toml`
- Layout inside `.machi/`: `{plan}/plan.md`, `{plan}/tasks/*.md`, `{plan}/context/*.md`

## Commands

```bash
machi <command>             # the installed CLI
uv sync                     # install deps
uv run basedpyright         # type check
uv run ruff check           # lint
uv run ruff format          # format
```

Verification for a change: targeted `pytest`, then the full suite, plus `ruff format`,
`ruff check`, and `basedpyright`. Checkout executable integration tests run the installed
`machi`/`machinate` scripts, so source changes are picked up through the editable install.

## Conventions

- Keep it simple — no servers, no databases, just files and TOML.
- CLI handles state mutations; skills handle AI workflow.
- Commands are thin: parse inputs, load settings/select formatter, call a service or setup
  function, render a Pydantic result. Register commands via the `CommandSpec` catalog.
- Add a `Result` model for each command and a matching `render_text` in `formatting.py`.
- Tests with `pytest`.

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
