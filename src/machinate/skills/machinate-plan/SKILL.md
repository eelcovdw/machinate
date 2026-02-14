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

4. **Write plan.md**: Edit the generated plan.md file to include the discussion results. Keep the existing frontmatter and title, add content below.

5. **Add context files** if the user has reference docs, specs, or research to include. Run `machi context add <name1> <name2> ...` and write content into each file.

6. **Break into tasks**: Discuss task breakdown with the user, then run `machi task add <name1> <name2> ...`. Write a description into each task file. Tasks should be concrete, one-session-sized units of work.

7. **Show the result**: Run `machi show` to display the final plan.

## Guidelines

- Use kebab-case for all names
- Prefix task filenames with numbers for ordering: `01-setup`, `02-api-layer`
- Keep plan.md focused on the what and why, put technical details in context files
- Tasks should be actionable — each one is a single Claude Code session
- Use relative Obsidian wiki-links for cross-references between plans: `[[../other-plan/plan]]`
