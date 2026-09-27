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

## Tests

Test Machinate, not its dependencies or its wording.

- Do not test third-party behavior: typer, rich, click, tantivy, pydantic, upath internals are out
  of scope. If a test can only pass or fail because of a library's implementation detail, delete it.
- Do not assert on rendered prose: help text, docstrings, error wording, or CLI output strings are
  free to change. Assert the structured result (models, exit codes, file state), not the sentence.
- Do not re-test one behavior at every layer. Cover it once, at the layer that owns the logic;
  a service test does not need a matching CLI test unless wiring is what changed.
- No test per fix by default. Add a regression test when the bug is subtle enough to come back
  silently (ordering, offsets, escaping, state transitions), not for mechanical changes.
- Weak tests are worse than no tests: they pin incidental behavior and break on unrelated edits.

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

`list` subcommands take repeatable `--tag`/`--status`, `--sort
name|created|updated`, `--descending`, `--limit`, and `--no-group` to drop
status grouping. Plan statuses are `draft|active|done`; task statuses are
`todo|in-progress|done`.
