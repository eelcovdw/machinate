# machinate

File-based project planning for Claude Code. Plans live as markdown in `.claude/plans/`, browsable in Obsidian.

## Install

```bash
uv tool install git+https://github.com/eelcovdw/machinate.git
```

## Usage

```bash
machi init                    # initialize a project (explicit -P or cwd)
machi plan add <name>         # create a new plan
machi plan list               # list plans
machi plan show [name]        # show plan details (default: current)
machi plan set <name>         # set current plan
machi plan status [status]    # print or set current plan's status
machi plan info [name]        # plan overview (default: current)
machi info                    # project overview
machi task add [name...]      # add tasks to current plan
machi task list               # list tasks grouped by status
machi task status <task> [s]  # print or set a task's status
machi context add [name...]   # add context docs
machi context list            # list context docs
```
