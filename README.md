# machinate

File-based project planning for Claude Code. Plans live as markdown in `.claude/plans/`, browsable in Obsidian.

## Install

```bash
uv tool install git+https://github.com/eelcovdw/machinate.git
```

## Usage

```bash
machi init                    # set up plans dir + symlink
machi new <name>              # create a new plan
machi list                    # list plans
machi show [name]             # show plan details (default: current)
machi set <name>              # set current plan
machi status [status]         # print or set current plan's status
machi task add [name...]      # add tasks to current plan
machi task list               # list tasks grouped by status
machi task status <task> [s]  # print or set a task's status
machi context add [name...]   # add context docs
machi context list            # list context docs
```
