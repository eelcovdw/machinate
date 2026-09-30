"""Shared helpers for the machinate agent evals: typed JSON access and machi calls.

Everything here talks to the working-tree machi. JSON values are narrowed with the
`as_*` helpers instead of `Any`, so the eval scripts type-check cleanly.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
MACHI = REPO_ROOT / ".venv" / "bin" / "machi"

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def parse_json(text: str) -> JsonValue:
    """Parse JSON text, mapping the untyped stdlib return onto `JsonValue`."""
    return cast("JsonValue", json.loads(text))


def as_dict(value: JsonValue) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def as_list(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def as_str(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""


def as_int(value: JsonValue) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def as_float(value: JsonValue) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def run_machi(project_dir: Path, *args: str, check: bool = True) -> str:
    """Run the working-tree machi in `project_dir` and return stdout."""
    completed = subprocess.run(  # noqa: S603 - runs the fixed working-tree machi
        [str(MACHI), *args],
        cwd=project_dir,
        capture_output=True,
        check=check,
        text=True,
    )
    if check and completed.returncode != 0:
        msg = f"machi {' '.join(args)} failed ({completed.returncode}): {completed.stderr}"
        raise RuntimeError(msg)
    return completed.stdout


def machi_json(project_dir: Path, *args: str) -> JsonValue:
    """Run the working-tree machi and parse its JSON output."""
    return parse_json(run_machi(project_dir, *args, "--format", "json"))


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class TaskState:
    name: str
    status: str
    summary: str
    body: str


@dataclass
class PlanState:
    name: str
    status: str
    body: str
    last_activity_at: str
    tasks: dict[str, TaskState]


@dataclass
class DocState:
    name: str
    summary: str
    body: str


@dataclass
class ProjectSnapshot:
    plans: dict[str, PlanState]
    docs: dict[str, DocState]
    state_hash: str


def _record_body(record: dict[str, JsonValue], key: str) -> str:
    return as_str(record.get(key))


def snapshot_project(project_dir: Path) -> ProjectSnapshot:
    """Read every plan, task, and doc through machi's JSON output."""
    plans: dict[str, PlanState] = {}
    for plan_entry in as_list(as_dict(machi_json(project_dir, "plan", "list")).get("plans")):
        name = as_str(as_dict(plan_entry).get("name"))
        if not name:
            continue
        plan = as_dict(machi_json(project_dir, "plan", "show", name))
        tasks: dict[str, TaskState] = {}
        for task_entry in as_list(
            as_dict(machi_json(project_dir, "task", "list", "-p", name)).get("tasks")
        ):
            task_name = as_str(as_dict(task_entry).get("name"))
            if not task_name:
                continue
            task = as_dict(machi_json(project_dir, "task", "show", "-p", name, task_name))
            record = as_dict(task.get("task"))
            tasks[task_name] = TaskState(
                name=task_name,
                status=as_str(as_dict(record.get("metadata")).get("status")),
                summary=as_str(record.get("summary")),
                body=as_str(task.get("body")),
            )
        plan_record = as_dict(plan.get("plan"))
        plans[name] = PlanState(
            name=name,
            status=as_str(as_dict(plan_record.get("metadata")).get("status")),
            body=_record_body(plan, "body"),
            last_activity_at=as_str(plan_record.get("last_activity_at")),
            tasks=tasks,
        )

    docs: dict[str, DocState] = {}
    for doc_entry in as_list(as_dict(machi_json(project_dir, "doc", "list")).get("docs")):
        name = as_str(as_dict(doc_entry).get("name"))
        if not name:
            continue
        doc = as_dict(machi_json(project_dir, "doc", "show", name))
        record = as_dict(doc.get("doc"))
        docs[name] = DocState(
            name=name,
            summary=as_str(record.get("summary")),
            body=_record_body(doc, "body"),
        )

    return ProjectSnapshot(
        plans=plans,
        docs=docs,
        state_hash=sha256_file(project_dir / ".machi" / "machinate.toml"),
    )
