---
name: machinate:resume
description: Resume work on a machinate plan in a new session
argument-hint: [plan-name]
disable-model-invocation: true
allowed-tools: Bash(machi *), Read
---

# Resume a machinate plan

You are catching up on an existing plan to continue work in a new Claude Code session.

## Current plan state

!`machi show $ARGUMENTS`

## Steps

1. **Read the plan**: Read the plan.md file shown above.

2. **Read all tasks**: Read each task file to understand what's been done and what's next. Pay attention to the `status` field in frontmatter (todo, in-progress, done).

3. **Read context** (if any): Read context files for background information.

4. **Summarize for the user**:
   - What we're building (1-2 sentences)
   - What's done (completed tasks)
   - What's in progress
   - What's next (first todo task)
   - Any relevant context or decisions

5. **Suggest next action**: Based on the first `todo` or `in-progress` task, suggest what to work on and ask the user if they want to proceed.

## Guidelines

- If no plan name is given as argument, use the current plan
- Be concise — the user wants to get back to work, not re-read everything
- Focus on actionable next steps
- If a task is `in-progress`, prioritize that over `todo` tasks
