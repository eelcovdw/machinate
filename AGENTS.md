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
- CLI entry point: `machi` / `machinate` (installed editable — do NOT use `uv run machi`)
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
