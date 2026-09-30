#!/usr/bin/env python3
"""Build the synthetic project the eval jobs run against, using the working-tree machi.

Run with `python -m evals.seed <directory>`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from .harness import MACHI, run_machi

# Facts seeded into docs; jobs.py asserts them against model answers.
INCIDENT_FACT = "clock skew"
INCIDENT_FIX = "NTP"

CONVENTIONS_BODY = """# Conventions

- Branches: `feature/<short-name>`, never commit to `main`.
- Tests sit next to the code they cover.
- Every behaviour change gets a one-line entry in the changelog.
"""

ARCHITECTURE_BODY = """# Architecture

The service is a single Python process. Storage is files and SQLite; there is no
server. The CLI owns all state mutations and the skills drive the workflow.
"""

DEPLOY_RUNBOOK_BODY = """# Deploy runbook

1. Run `uv run pytest` and wait for green.
2. Build the container with the release tag.
3. Roll out one host at a time and watch the error rate for five minutes.
"""

INCIDENT_BODY = f"""# Incident: 2025-03 website outage

The March 2025 outage was caused by {INCIDENT_FACT} in the session service:
expired tokens were accepted because host clocks had drifted apart. It was
resolved by enabling {INCIDENT_FIX} (chrony) on every app host.
"""

ONCALL_BODY = """# On-call

Page the primary for any sustained error-rate alert. The secondary only joins when
the primary has not acknowledged within ten minutes.
"""

DECISIONS_BODY = """# Decisions

- **Sessions**: opaque server-side tokens, not JWTs.
- **Cookies**: `HttpOnly` and `SameSite=Lax`.
"""

GLOSSARY_BODY = """# Glossary

- **Plan**: a unit of planned work with tasks and context docs.
- **Task**: a single, ordered step inside a plan.
- **Doc**: project-wide reference material, not tied to one plan.
"""

DOCS: tuple[tuple[str, str, str], ...] = (
    ("conventions", "Repository conventions", CONVENTIONS_BODY),
    ("architecture", "System architecture overview", ARCHITECTURE_BODY),
    ("deploy-runbook", "How to deploy a release", DEPLOY_RUNBOOK_BODY),
    ("incident-2025-03", "Postmortem for the March 2025 outage", INCIDENT_BODY),
    ("oncall", "On-call rotation and escalation", ONCALL_BODY),
    ("glossary", "Domain terms", GLOSSARY_BODY),
)


def write_body(project_dir: Path, args: list[str], body: str) -> None:
    """Write a body to the resource `args` resolves to, preserving its frontmatter."""
    path = Path(run_machi(project_dir, *args, "--format", "text").strip())
    lines = path.read_text().splitlines(keepends=True)
    frontmatter = ""
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                frontmatter = "".join(lines[: index + 1])
                break
    path.write_text(frontmatter + "\n" + body)


def _create_plan(project_dir: Path, name: str, status: str, task_names: list[str]) -> None:
    run_machi(project_dir, "plan", "add", name, "--status", status)
    for task_name in task_names:
        run_machi(project_dir, "task", "add", "-p", name, task_name)


def seed_project(project_dir: Path) -> None:
    """Populate `project_dir` with the shared eval project."""
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)
    subprocess.run(  # noqa: S603 - fixed working-tree machi
        [str(MACHI), "init"], cwd=project_dir, check=True, capture_output=True, text=True
    )

    _create_plan(project_dir, "auth", "active", ["01-login-form", "02-session-cookie", "03-logout"])
    write_body(
        project_dir,
        ["plan", "path", "auth"],
        "# Auth\n\nSign-up, login, and session handling for the web app.\n",
    )
    run_machi(project_dir, "task", "update", "-p", "auth", "01-login-form", "--status", "done")
    write_body(
        project_dir,
        ["task", "path", "-p", "auth", "01-login-form"],
        "# Login form\n\nShipped a form that posts credentials and shows inline errors.\n",
    )
    run_machi(project_dir, "context", "add", "-p", "auth", "decisions")
    write_body(project_dir, ["context", "path", "-p", "auth", "decisions"], DECISIONS_BODY)

    _create_plan(
        project_dir, "billing", "active", ["01-invoice-model", "02-stripe-webhook", "03-refunds"]
    )
    run_machi(
        project_dir, "task", "update", "-p", "billing", "01-invoice-model", "--status", "done"
    )
    run_machi(
        project_dir,
        "task",
        "update",
        "-p",
        "billing",
        "02-stripe-webhook",
        "--status",
        "in-progress",
    )
    write_body(
        project_dir,
        ["task", "path", "-p", "billing", "01-invoice-model"],
        "# Invoice model\n\nInvoice and line-item tables are in place and covered by tests.\n",
    )

    _create_plan(project_dir, "search", "draft", ["01-index-schema", "02-query-parser"])

    for name, summary, body in DOCS:
        run_machi(project_dir, "doc", "add", name, "--summary", summary)
        write_body(project_dir, ["doc", "path", name], body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = cast("Path", args.directory)
    seed_project(directory)
    sys.stdout.write(json.dumps({"seeded": str(directory)}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
