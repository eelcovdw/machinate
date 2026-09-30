# Machinate — Agent Instructions

File-based project planning CLI for Claude Code.

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

- Locate work with `machi search QUERY` before any `ls`/`find`/plan enumeration.
- Answer a question with at most a couple of commands; do not audit.
- A question is not a work order. "What's next" means list the remaining tasks, not start them.
  Read files, run commands, or make edits only when the current request asks for it.
- A docs task is one gather and one edit — no read-backs and no live verification of text you
  just wrote from the real CLI.
- No live demo when the tests already cover the behavior.
- Run the verification suite **once per change**, after all edits are done: targeted pytest,
  then the full suite, then `ruff format`, `ruff check`, `basedpyright`. Do not re-run tests or
  linters after a formatting-only, comment-only, or notes-only change, and do not repeat the
  suite to confirm something already verified.
- **Task status and tracking live on machinate tasks. Never maintain task lists or statuses
  inside a plan body (`plan.md`) — the plan is the spec, tasks are the tracker.**
- Stop when the request is satisfied. No post-completion bookkeeping (plan bodies, temp
  cleanup, status syncing) unless asked.
- Run everything through `uv` (`uv run machi …`, `uv run pytest`, …) — do not manually
  `source .venv/bin/activate`.

## Stack

- Python 3.14, uv, src layout (`src/machinate/`)
- CLI entry point: `machi` / `machinate`. `uv run machi …` runs the working tree (the project
  venv has an editable install). The global `machi` is a separate, non-editable tool install:
  never use it to check code changes.
- CLI framework: `typer`
- Storage: a real `.machi/` directory per project, state in `.machi/machinate.toml`
- Layout inside `.machi/`: `plans/{plan}/plan.md`, `plans/{plan}/tasks/*.md`,
  `plans/{plan}/context/*.md`, `docs/*.md`

## Commands

```bash
uv run machi <command>      # the working-tree CLI
uv sync                     # install deps
uv run basedpyright         # type check
uv run ruff check           # lint
uv run ruff format          # format
```

Verification for a change: targeted `pytest`, then the full suite, plus `ruff format`,
`ruff check`, and `basedpyright`. The console-script tests run the venv's `machi` launcher,
which picks up source changes through the editable install.

## Conventions

- Keep it simple — no servers, no databases, just files and TOML.
- CLI handles state mutations; skills handle AI workflow.
- Commands are thin: parse inputs, load settings/select formatter, call a service or setup
  function, render a Pydantic result. Register commands via the `CommandSpec` catalog.
- Add a `Result` model for each command and a matching `render_text` in `formatting.py`.
- Tests with `pytest`.

## Python engineering

### Layering

- Dependencies point one way: `cli` → `services` → `storage`, with `models` shared. Storage
  knows nothing about plans-as-workflow or output; services know nothing about typer, rich, or
  formats. CLI code does not read or write store files directly; project discovery and
  `init` (`cli/project_setup.py`) are the exception.
- Put logic in the layer that owns it. If a command needs a new rule, it belongs in a service;
  if a service needs a new path or file operation, it belongs in storage (`Layout`,
  `DocumentStore`).
- Layers are a navigation aid, not a doctrine. Don't split data models per layer unless the
  code demands it: if storage, services, and CLI would each need a near-identical model, use one
  shared model instead. It's a trade-off. Be consistent, not pedantic about separation of
  concerns.
- No rigid architecture patterns (DDD, hexagonal, ports-and-adapters, and so on). The
  goals are readability, easy navigation, and easy future changes.
- Pass dependencies in through constructors (`DocService(document_store, layout)`). No module
  globals holding state, no singletons, no work at import time.
- Before adding a helper, look for an existing one (`services/batch.py`, `storage/queries.py`,
  `cli/formatting.py`). Extend it rather than writing a near-copy for one resource type.
  Plan, task, context, and doc should behave the same unless there is a reason they differ.

### Types and data

- Code must pass `basedpyright` with no new suppressions. Fix the type rather than silencing it.
  `cast` and `# pyright: ignore[rule]` are only for untyped third-party boundaries (ruamel,
  `get_args`) and always name the specific rule.
- No `Any`. Use `object` for truly unknown values and narrow with `isinstance`.
- Modern syntax only: `list[str]`, `X | None`, `type` aliases, `Self`, `@override`. Never
  `typing.List`, `Optional`, or `Union`.
- Pydantic `BaseModel` for anything that crosses a boundary: files, CLI input, command results,
  JSON output. Validate once at the edge (`@validate_call` on public service methods, constrained
  `Annotated` types like `Name`); internal `_` methods trust their inputs.
- Encode invariants in types, not in comments or runtime checks scattered around: `Literal`
  status values, constrained names and paths, required fields without defaults.
- Store the source of truth and derive the rest. Don't duplicate a value (counts, paths, flags)
  when it can be computed from what is already stored.
- Use `PurePosixPath` for store-relative paths and `Path` only where the real filesystem is
  touched.

### Functions and APIs

- Small functions with one job. Early returns over nested conditionals.
- Keyword-only parameters (`*,`) for anything optional or easy to mix up. Required parameters
  come first. Prefer two clear functions over one function with a boolean mode flag (typer
  command signatures excepted).
- Return values, don't mutate arguments. No mutable default arguments.
- Return a dataclass (or Pydantic model at a boundary) instead of a tuple when naming the
  fields makes the call site clearer, e.g. several values of the same type or results that get
  passed around. A tuple is fine for a local one-off whose meaning is obvious from the function
  name.

### Naming

- Nouns for properties, verbs for methods. Nobody should have to guess whether a name needs
  parentheses. `record.summary` as a property is right; `record.summary()` as a method or a
  `get_summary` property is wrong. `calculate_summary()` is right.
- Properties are cheap and side-effect free: no file I/O, no heavy computation, no mutation.
  If it reads a file or does real work, it's a method (`read_summary()`).
- Names say what the code does, up to a point. A function that returns the stored summary or
  derives one from the body is `determine_summary()`, not `get_summary()` (hides the
  fallback) and not `get_summary_or_derive_from_body()` (too much).
- Full consistency: one word per concept and one verb per operation, across the whole codebase
  and the public surface. `find` vs `search` vs `get_all` for the same thing is a bug. Verb
  meanings:
  - `get_x`: look up one; raises if missing.
  - `find_x`: look up; may return `None`.
  - `list_x`: return many.
  - `read_x` / `write_x`: touch the filesystem.
  - `create_x`: make a new one; fails if it exists.
  - `build_x` / `to_x`: pure construction or conversion.
- Booleans read as questions: `is_valid`, `has_tasks`, `exists`.
- Qualify names when the kind is ambiguous: `relative_path` vs `absolute_path`, a raw input
  name vs a validated one.
- The same rules apply to the public surface: JSON field names, CLI flags, command names. Two
  names for the same value (`modified_at` vs `last_activity_at`) is a naming bug.
- Name things after the domain (`plan`, `task`, `context`, `doc`, `store`, `layout`). No type
  suffixes (`name_str`, `plans_list`). No vague names outside local scope: `data`, `result`,
  `handle`, `process`, `manager`, `utils.py`, `helpers.py`.
- Short names are fine for locals and temporaries, and common abbreviations (`idx`, `ctx`,
  `i`, `fn`) are fine anywhere they are idiomatic.

### Explicit over magic

- Keep Python magic to a minimum. Metaprogramming, custom decorators, dynamic code generation,
  `getattr`/`setattr` by string, registries, and implicit conversion all have their place, but
  use them only when they clearly pay for themselves. Default to plain, explicit code.
- Slightly more verbose always beats a condensed shortcut that is hard to read or hides what
  happens.
- Example: converting generated Protobuf messages to Pydantic models. Wrong: dump the message to
  a dict and feed it to `Model.model_validate`. Right: build the model with each field mapped
  explicitly. The explicit version keeps full type checking, has no hidden behavior, and has no
  spot where a renamed or mistyped field slips through silently. A new field then needs new
  code, and that's the point: the change is visible and reviewed.

### Simplicity and taste

These are judgment calls, not rules to apply mechanically. Behind all of them are three
questions to ask of any piece of code:

- Would we miss it if it were gone?
- Does it make future changes easier or harder?
- Does it make the codebase easier or harder to understand and navigate?

Code that fails these questions isn't worth keeping, however tidy it looks.

- Explicit is not the same as ceremonious. Spelling out logic and field mappings is good;
  wrapping them in extra layers, helpers, and boilerplate usually isn't.
- Let abstractions earn their place. A `Protocol`, base class, generic, context manager, or
  small wrapper type tends to pay off once there are several real users or it clearly
  simplifies the callers. With one caller, inlining is often the better first version.
- Be suspicious of code that only passes things along: a function that forwards to another,
  a class that wraps one call, a config object for two parameters.
- Use a pattern because this code needs it, not out of habit. `__all__` in internal modules,
  `frozen`/`slots` on every dataclass, checks for states the types already rule out, and
  `try`/`except` that re-raises unchanged are common examples of habit.
- Weigh cost against benefit. A cosmetic gain rarely justifies a new code path, a slower
  hot path, or a test that has to fake the environment.
- Fewer, larger modules organized by concept usually read better than many small files. A
  300-line module is fine; a 15-line module often belongs in its neighbor.
- Keep prose short. Docstrings and comments say what isn't obvious from the code; module
  docstrings are a line or two.
- Tests follow the same taste: a plain, readable test beats a clever fixture setup, and
  parametrizing only helps when the cases really share a shape.

### Errors

- Raise specific exceptions from the owning layer's hierarchy (`StorageError` subclasses in
  storage). Never raise or catch bare `Exception`; never swallow an error silently.
- Wrap lower-level exceptions with context (`raise X(...) from err`) and keep the original as
  the cause. Translate to user-facing messages and exit codes only in the CLI.
- Fail loudly on invalid state instead of guessing a fallback. A missing or corrupt file is an
  error, not an empty result.
- File writes that replace existing content go through `storage/atomic.py`.

### Style and hygiene

- `ruff` runs with `select = ["ALL"]`. Satisfy the rule; add a `# noqa: RULE` only with a short
  reason, and don't add per-file ignores without asking.
- Imports at module top. Deferred imports are only allowed where startup time matters (CLI,
  `document_store.py`) and are already sanctioned in `pyproject.toml`.
- Comments explain *why*, not *what*. Docstrings are one line unless the contract is subtle;
  don't restate the signature.
- Never reference task, plan, or triage identifiers in code (comments, docstrings, names).
  Readers have no access to them; state the reason in place.
- No dead code, commented-out code, speculative parameters, or abstractions with one
  implementation "for later". Delete code that becomes unused as part of your change.
- Standard library first. Don't add a dependency without asking.

## Tests

Test Machinate, not its dependencies or its wording.

- Do not test third-party behavior: typer, rich, click, tantivy, pydantic internals are out
  of scope. If a test can only pass or fail because of a library's implementation detail, delete it.
- Do not assert on rendered prose: help text, docstrings, error wording, or CLI output strings are
  free to change. Assert the structured result (models, exit codes, file state), not the sentence.
- Do not re-test one behavior at every layer. Cover it once, at the layer that owns the logic;
  a service test does not need a matching CLI test unless wiring is what changed.
- No test per fix by default. Add a regression test when the bug is subtle enough to come back
  silently (ordering, offsets, escaping, state transitions), not for mechanical changes.
- Weak tests are worse than no tests: they pin incidental behavior and break on unrelated edits.

## Machinate

Plans, tasks, context, and docs are plain Markdown files with YAML frontmatter
under `.machi/` — no server, no database. This project is planned with
machinate; regenerate this section with `machi instructions`.

### Targeting

- Agents always pass `-p NAME`. Without it the current plan is used; select one
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
