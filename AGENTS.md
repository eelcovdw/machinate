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

## Stack

- Python 3.14, uv, src layout (`src/machinate/`)
- CLI entry point: `machi` / `machinate` (installed editable — do NOT use `uv run machi`).
  If it is not on your PATH, activate the venv first: `source .venv/bin/activate`.
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

machinate is a file-based planning tool for coding agents. It keeps a project's
plans, tasks, and context as plain Markdown with TOML frontmatter under `.machi/`,
with no server or database, and this project is planned with it.

Prefer the `machi` CLI over `ls`/`find`/`Glob` — it returns structured output and
keeps links consistent.

### Commands

```text
machi init          Initialize a project directory.
machi info          Show a project overview.
machi find          Search files under the project's .machi store (all plans).
machi instructions  Print this block.
machi schema        Print the JSON Schema for command results.
machi plan          add, list, show, info, path, set, update
machi task          add, list, show, info, path, update
machi context       add, list, show, info, path, update
```

### Finding work across plans

`machi find QUERY` is the cross-plan search — use it as the first step when you
know a task/document by name or phrase but not its plan. It searches every plan
unless you pass `-p`, so it replaces enumerating plans by hand.

```bash
machi find atomic-state-writes          # locate a task across all plans
machi find "atomic state" -p review-storage-fixes   # scope to one plan
machi find 'body:"truncates machinate.toml"'        # body-field phrase search
machi find --glob 'tasks/*.md'          # omit QUERY to list by filesystem glob
```

Results are path + line range + snippets (`plans/<plan>/tasks/<task>.md:1-7`).
The query language supports terms (fuzzy + prefix by default), `"phrases"`,
`field:term` (`path:`/`body:`), `+`/`-`, `AND`/`OR`/`NOT`, `term^2`, ranges
(`field:[a TO c]`), and set membership. Disable fuzziness with `--exact`; allow
field-scoped regexes with `--regex`. Tune output with `--context N`,
`--snippet-chars`, `--no-snippets`, and `--limit`. Prefer `find` over
`grep`/`rg`/`ls` for `.machi` content — it understands the store layout.

For narrower listings, `machi plan list` / `machi task list` / `machi context list`
accept `--search`, `--search-body`, repeatable `--tag` and `--status`, `--sort
name|created|updated`, `--descending`, and `--limit`. Plan statuses are
`draft|active|done`; task statuses are `todo|in-progress|done`.

### Targeting

- Target a plan with `-p NAME`; without it the current plan is used. **If no
  current plan is set, plan-scoped commands fail with `No current plan is
  selected` — pass `-p NAME` explicitly.**
- Select a current plan explicitly with `machi plan set -p NAME`.
- Non-interactive mode (`MACHI_INTERACTIVE=false`) requires `-p`.
- `-P DIR` targets an exact project directory; otherwise machinate discovers the
  nearest `.machi/` by walking upward.

### Output

- Use `--format text|json`. Precedence: `--format` > `MACHI_FORMAT` > default
  (text, or json in non-interactive mode).
- `machi schema` documents the exact JSON shape of every command result; pass a
  command path (e.g. `machi schema task show`) to narrow it.

### Editing

- `machi plan path`, `machi task path NAME`, and `machi context path NAME` print
  absolute editing paths; edit bodies with your own file tools. Their `path`
  subcommands also accept no name to print the containing directory.
- Change status, tags, and summaries with `machi plan|task|context update`; e.g.
  `machi task update NAME --status in-progress --tag x`. `--tag` replaces the
  tag set, and an empty `--summary ''` clears the summary.
- Inspect metadata without the body via `machi task info NAME` / `machi context
  info NAME`; `machi plan info` and `machi info` show overviews.
