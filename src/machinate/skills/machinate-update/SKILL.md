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

1. **Read all task files**: Read each task file listed above. Check the `status` frontmatter field and the task description.

2. **Assess what changed**: Look at the conversation history to understand what was worked on, completed, or discovered during this session.

3. **If instructions were given** (via argument), follow them — e.g. "mark tasks 01 and 02 done", "add a note about the API change", "update the approach section".

4. **If no instructions**, ask the user what to update. Suggest changes based on what you see:
   - Tasks that look completed → offer to mark `done`
   - Tasks that were started → offer to mark `in-progress`
   - New decisions or scope changes → offer to update plan.md
   - New tasks discovered → offer to create them via `machi task add`
   - Summaries missing from frontmatter → add them

5. **Apply updates**: Edit frontmatter `status` fields and file content as confirmed by the user.

6. **Show the result**: Run `machi show` to display the updated plan.

## Guidelines

- Only update what the user confirms — don't silently change things
- Always add a `summary` to frontmatter if it's missing — for plans, tasks, and context files
- Keep edits minimal — update statuses and add notes, don't rewrite task descriptions
- If the plan status should change (e.g. all tasks done → `status: done`), suggest it
