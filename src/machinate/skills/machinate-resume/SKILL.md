---
name: machinate:resume
description: Resume work on a machinate plan in a new session
argument-hint: [plan-name]
disable-model-invocation: true
allowed-tools: Bash(machi *), Read
---

# Resume a machinate plan

You are catching up on an existing plan to continue work in a new Claude Code session.

IMPORTANT: Do NOT use `ls`, `find`, `Glob`, or any filesystem discovery tools on plan directories. Use `machi` CLI commands for listing and discovering files. Use `Read` only for reading file contents that the CLI doesn't already provide. Do NOT re-read or re-fetch anything `machi show` already shows below.

## Current plan state

!`machi show $ARGUMENTS`

## Steps

The `machi show` output above already contains the plan content and task summaries. Use it — do not re-read files the CLI already showed you.

1. **Review the plan state**: The `machi show` output above has the plan content, task list, and statuses. Use this as your primary source.

2. **Read the project file**: Run `machi info` to find the project file, then read it for overall project context.

3. **Check context files**: Run `machi context list`. If there are context files relevant to the next task, read them.

4. **Read the next task file**: Identify the first `in-progress` or `todo` task from the task list above and read that task file for its full description.

5. **Summarize for the user**:
   - What we're building (1-2 sentences)
   - What's done (completed tasks)
   - What's in progress
   - What's next (first todo task)
   - Any relevant context or decisions

6. **Suggest next action**: Based on the first `in-progress` or `todo` task, suggest what to work on and ask the user if they want to proceed.

## CLI commands

```
machi show [name]           # show plan details, tasks, and content (no args = current plan)
machi list                  # list all plans with progress
machi task list             # list tasks grouped by status
machi context list          # list context files for current plan
machi info                  # show project status
```

## Rules

- **Always use `machi` commands** for listing and discovering files — never use `ls`, `find`, or `Glob` on plan directories
- Only use `Read` for file contents that the CLI doesn't already provide (e.g. reading a specific task's full description)
- If no plan name is given as argument, use the current plan
- Be concise — the user wants to get back to work, not re-read everything
- Focus on actionable next steps
- If a task is `in-progress`, prioritize that over `todo` tasks
