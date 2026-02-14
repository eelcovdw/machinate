---
name: machinate:plan
description: Create a new machinate plan with context and tasks
argument-hint: [plan-name]
disable-model-invocation: true
allowed-tools: Bash(machi *), Read, Edit, Write
---

# Create a machinate plan

You are creating a structured plan for a feature using machinate.

## Current state

!`machi list`

## Steps

1. **Get the plan name**: If invoked as `/machinate:plan <name>`, use that name. Otherwise ask the user what they want to build and derive a kebab-case name.

2. **Create the plan**: run `machi new <name>` to create the plan folder with frontmatter. This also sets it as the current plan.

3. **Discuss the plan** with the user:
   - What are we building and why?
   - What's the approach?
   - Any constraints or decisions?
   - What's in scope / out of scope?

4. **Write the plan file**: Edit the generated `plan-{name}.md` file to include the discussion results. Keep the existing frontmatter and title, add content below. Add a `summary` to the frontmatter — a short one-line description of the plan. Include a `[[../project-{name}]]` wiki-link near the top of the plan (run `machi info` to find the project file name).

5. **Add context files** if the user has reference docs, specs, or research to include. Run `machi context add <name1> <name2> ...` and write content into each file. Add a `summary` to each file's frontmatter.

6. **Break into tasks**: Discuss task breakdown with the user, then run `machi task add <name1> <name2> ...`. Write a description into each task file. Add a `summary` to each task's frontmatter — a short one-line description of what the task does. Tasks should be concrete, one-session-sized units of work.

7. **Show the result**: Run `machi show` to display the final plan.

## CLI commands

Use these `machi` commands for all state and file operations:

```
machi new <name>            # create plan folder + plan-{name}.md with frontmatter, sets as current
machi set <name>            # set current plan
machi show [name]           # show plan details (no args = current plan)
machi list                  # list all plans with progress
machi task add <name...>    # create task files with frontmatter
machi task list             # list tasks grouped by status
machi context add <name...> # create context files with frontmatter
machi context list          # list context files for current plan
machi info                  # show project status
```

## Rules

- **Always use `machi` commands** for creating and listing files — never use `ls`, `find`, `Glob`, or `mkdir` on plan directories
- Only use `Read`/`Edit`/`Write` for reading and editing file contents, not for discovering or listing files
- Use kebab-case for all names
- Prefix task filenames with numbers for ordering: `01-setup`, `02-api-layer`
- Keep the plan file focused on the what and why, put technical details in context files
- Tasks should be actionable — each one is a single Claude Code session
- Use relative Obsidian wiki-links for cross-references between plans: `[[../other-plan/plan-other-plan]]`
