---
name: machinate:update
description: Update the current plan — sync task statuses, edit plan/task content
argument-hint: [instructions]
disable-model-invocation: true
allowed-tools: Bash(machi *), Read, Edit
---

# Update a machinate plan

You are updating the current plan to reflect work that's been done in this session.

## Current plan state

!`machi show`

## Steps

The `machi show` output above already contains the plan content and task summaries with statuses. Use it — do not re-read files the CLI already showed you.

1. **Review task statuses**: The `machi show` output above has the task list with statuses and summaries. Use this as your primary source. Only read a specific task file if you need its full description to assess changes.

2. **Assess what changed**: Look at the conversation history to understand what was worked on, completed, or discovered during this session.

3. **If instructions were given** (via argument), follow them — e.g. "mark tasks 01 and 02 done", "add a note about the API change", "update the approach section".

4. **If no instructions**, ask the user what to update. Suggest changes based on what you see:
   - Tasks that look completed → offer to mark `done` via `machi task status <file> done`
   - Tasks that were started → offer to mark `in-progress` via `machi task status <file> in-progress`
   - New decisions or scope changes → offer to update plan content
   - New tasks discovered → offer to create them via `machi task add`
   - Summaries missing from frontmatter → add them

5. **Apply updates**:
   - Use `machi task status <file> <status>` to change task statuses
   - Use `machi task add <name...>` to create new tasks
   - Use `Edit` only for changing file content (descriptions, plan sections, frontmatter summaries)

6. **Show the result**: Run `machi show` to display the updated plan.

## CLI commands

```
machi show [name]           # show plan details (no args = current plan)
machi list                  # list all plans with progress
machi task add <name...>    # create task files with frontmatter
machi task status <file> <status>  # set a task's status (todo, in-progress, done)
machi task list             # list tasks grouped by status
machi context add <name...> # create context files with frontmatter
machi context list          # list context files for current plan
machi set <name>            # set current plan (auto-activates)
machi status [status]       # print or set current plan's status
```

## Rules

- **Always use `machi` commands** for listing, discovering, and changing statuses — never use `ls`, `find`, or `Glob` on plan directories
- Use `machi task status` for status changes, not manual frontmatter edits
- Only use `Read` for file contents that the CLI doesn't already provide
- Only update what the user confirms — don't silently change things
- Always add a `summary` to frontmatter if it's missing — for plans, tasks, and context files
- Keep edits minimal — update statuses and add notes, don't rewrite task descriptions
- If the plan status should change (e.g. all tasks done → `status: done`), suggest it
