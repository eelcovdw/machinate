---
name: machinate:init
description: Initialize machinate and create a project description file
disable-model-invocation: true
allowed-tools: Bash(machi *), Read, Edit, Glob
---

# Initialize machinate

You are setting up machinate for this project and writing the project description file.

## Steps

1. **Run init**: Run `machi init -y` to create the plans directory, install skills, and set up permissions. This creates a `project-{name}.md` file in `.claude/plans/`.

2. **Gather project context**: Build a short project description from existing sources, checked in this order:
   - **CLAUDE.md** (preferred): Read `CLAUDE.md` at the project root. If it exists, extract the project description, stack, conventions, and key architectural decisions. This is usually the best source.
   - **README**: If no CLAUDE.md, read `README.md` for project description and setup info.
   - **Quick code scan**: If neither exists, do a quick scan — check `package.json`, `pyproject.toml`, `Cargo.toml`, or similar for project name/description, then glance at the top-level directory structure.

3. **Write the project file**: Run `machi info` to find the project file path, then edit it. Add a concise project description below the heading. Include:
   - What the project is (1-2 sentences)
   - Stack / key technologies
   - Key conventions or architectural decisions
   - Keep it short — this is a reference card, not documentation. Aim for 10-20 lines of content.
   - Add a `summary` to the frontmatter — a one-line description of the project.

4. **Show the result**: Print the project file path so the user can review it.

## CLI commands

Use these `machi` commands for all state and file operations:

```
machi init [-y]             # create plans dir, install skills, set up permissions
machi info                  # show project status
machi list                  # list all plans with progress
machi show [name]           # show plan details (no args = current plan)
```

## Rules

- **Always use `machi` commands** for creating and listing plan files — never use `ls`, `find`, or `Glob` on plan directories
- Only use `Read`/`Edit` for reading and editing file contents (CLAUDE.md, README, project file), not for discovering plan files
- Don't ask the user questions — just gather context and write a reasonable first draft
- Keep the project file concise and scannable
- Don't duplicate CLAUDE.md verbatim — distill the key points relevant to planning
- If the project is already initialized, skip step 1 and just populate the project file
