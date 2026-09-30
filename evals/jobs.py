"""Eval jobs: prompt(s), golden path, and an end-state checker for each."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .harness import DocState, ProjectSnapshot, TaskState
from .seed import INCIDENT_FACT, INCIDENT_FIX, seed_project

MIN_FEATURE_TASKS = 3

PICK_UP_WORK_PROMPT = """You are working in a project managed by the `machi` CLI. Find the
next task to work on in the `auth` plan: list its todo tasks and pick the first one. Then
write a 3-5 bullet implementation plan into that task's body and mark the task in-progress.
Always pass `-p auth` to plan-scoped machi commands. Report which task you picked and the
absolute path of its file."""

PLAN_FEATURE_PROMPT = """Create a plan for a password reset feature, using the `machi`
CLI. Create a new active plan named exactly `password-reset` and give it a short body
describing the feature. Add at least three tasks whose names sort in order (start each with
a number, e.g. `01-...`); every task must have a one-line summary set when it is created.
Pass `-p password-reset` to task commands. Report the plan name and its tasks."""

RECORD_DOC_PROMPT = """Record a project decision as a doc using the `machi` CLI. Create a
doc named exactly `secret-storage` with the summary `Where application secrets are stored`.
Write a body stating that secrets live in Vault at path `secret/machinate` and are never
committed to the repository. Report the doc name and its file path."""

RECALL_DOC_PROMPT = """Answer this question using the project's docs: What caused the
March 2025 outage, and how was it fixed? Reply with the answer only."""

ANSWER_QUESTION_PROMPT = """Answer two questions about this machinate project, in one
line: (1) how many tasks are done in the `billing` plan? (2) which plan had the most recent
activity? Mention both answers."""

TWO_AGENTS_PROMPTS = (
    """You are agent A. In the `auth` plan, find the todo tasks and mark the
highest-numbered todo task as done. Only touch the `auth` plan. Report what you changed.""",
    """You are agent B. In the `billing` plan, find the todo tasks and mark the
highest-numbered todo task as done. Only touch the `billing` plan. Report what you
changed.""",
)


@dataclass
class CheckResult:
    passed: bool
    reasons: list[str]


@dataclass(frozen=True)
class Job:
    name: str
    prompts: tuple[str, ...]
    golden_path: tuple[str, ...]
    checker: Callable[[ProjectSnapshot, ProjectSnapshot, list[str]], CheckResult]
    seed: Callable[[Path], None] = seed_project


def _task(snapshot: ProjectSnapshot, plan: str, task: str) -> TaskState | None:
    plan_state = snapshot.plans.get(plan)
    return None if plan_state is None else plan_state.tasks.get(task)


def _task_differs(before: ProjectSnapshot, after: ProjectSnapshot, plan: str, task: str) -> bool:
    old = _task(before, plan, task)
    new = _task(after, plan, task)
    if old is None or new is None:
        return old is not new
    return (old.status, old.summary, old.body) != (new.status, new.summary, new.body)


def _doc_differs(before: ProjectSnapshot, after: ProjectSnapshot, doc: str) -> bool:
    old: DocState | None = before.docs.get(doc)
    new: DocState | None = after.docs.get(doc)
    if old is None or new is None:
        return old is not new
    return (old.summary, old.body) != (new.summary, new.body)


def _contains(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def _changed_others(
    before: ProjectSnapshot, after: ProjectSnapshot, plan: str, keep: set[str]
) -> list[str]:
    plan_state = before.plans[plan]
    return [
        f"{plan}/{name} changed but should not have"
        for name in plan_state.tasks
        if name not in keep and _task_differs(before, after, plan, name)
    ]


def check_pick_up_work(
    before: ProjectSnapshot, after: ProjectSnapshot, _outputs: list[str]
) -> CheckResult:
    reasons: list[str] = []
    target = _task(after, "auth", "02-session-cookie")
    if target is None:
        reasons.append("auth/02-session-cookie is missing")
    else:
        if target.status != "in-progress":
            reasons.append(
                f"auth/02-session-cookie status is {target.status!r}, want 'in-progress'"
            )
        if not target.body.strip():
            reasons.append("auth/02-session-cookie body is empty")
    reasons += _changed_others(before, after, "auth", {"02-session-cookie"})
    return CheckResult(passed=not reasons, reasons=reasons)


def check_plan_feature(
    _before: ProjectSnapshot, after: ProjectSnapshot, _outputs: list[str]
) -> CheckResult:
    plan = after.plans.get("password-reset")
    if plan is None:
        return CheckResult(passed=False, reasons=["plan 'password-reset' was not created"])
    task_names = sorted(plan.tasks)
    reasons: list[str] = []
    if plan.status != "active":
        reasons.append(f"plan status is {plan.status!r}, want 'active'")
    if not plan.body.strip():
        reasons.append("plan body is empty")
    if len(task_names) < MIN_FEATURE_TASKS:
        reasons.append(f"plan has {len(task_names)} tasks, want at least {MIN_FEATURE_TASKS}")
    if task_names and not all(re.match(r"^\d+", name) for name in task_names):
        reasons.append("task names are not numbered")
    if task_names != list(plan.tasks):
        reasons.append("tasks do not sort in creation order")
    reasons += [
        f"task {name} has no summary"
        for name, task in plan.tasks.items()
        if not task.summary.strip()
    ]
    return CheckResult(passed=not reasons, reasons=reasons)


def check_record_doc(
    _before: ProjectSnapshot, after: ProjectSnapshot, _outputs: list[str]
) -> CheckResult:
    doc = after.docs.get("secret-storage")
    if doc is None:
        return CheckResult(passed=False, reasons=["doc 'secret-storage' was not created"])
    reasons: list[str] = []
    if not doc.summary.strip():
        reasons.append("doc has no summary")
    if not _contains(doc.body, "Vault"):
        reasons.append("doc body does not mention Vault")
    if not _contains(doc.body, "secret/machinate"):
        reasons.append("doc body does not mention secret/machinate")
    return CheckResult(passed=not reasons, reasons=reasons)


def check_recall_doc(
    _before: ProjectSnapshot, _after: ProjectSnapshot, outputs: list[str]
) -> CheckResult:
    answer = "\n".join(outputs)
    reasons: list[str] = []
    if not _contains(answer, INCIDENT_FACT):
        reasons.append(f"answer does not contain {INCIDENT_FACT!r}")
    if not re.search(rf"\b{re.escape(INCIDENT_FIX)}\b", answer, re.IGNORECASE):
        reasons.append(f"answer does not contain {INCIDENT_FIX!r}")
    return CheckResult(passed=not reasons, reasons=reasons)


def check_answer_question(
    before: ProjectSnapshot, _after: ProjectSnapshot, outputs: list[str]
) -> CheckResult:
    answer = "\n".join(outputs)
    reasons: list[str] = []
    if not re.search(r"\b(1|one)\b", answer, re.IGNORECASE):
        reasons.append("answer does not state that 1 task is done in billing")
    if before.plans:
        most_recent = max(before.plans, key=lambda name: before.plans[name].last_activity_at)
        if not _contains(answer, most_recent):
            reasons.append(f"answer does not name the most recently active plan {most_recent!r}")
    return CheckResult(passed=not reasons, reasons=reasons)


def check_two_agents(
    before: ProjectSnapshot, after: ProjectSnapshot, _outputs: list[str]
) -> CheckResult:
    reasons: list[str] = []
    expected = {"auth": "03-logout", "billing": "03-refunds"}
    for plan, task in expected.items():
        state = _task(after, plan, task)
        if state is None or state.status != "done":
            status = "missing" if state is None else state.status
            reasons.append(f"{plan}/{task} is {status!r}, want 'done'")
    for plan, task in expected.items():
        reasons += _changed_others(before, after, plan, {task})
    if set(after.plans) != set(before.plans):
        reasons.append("plan set changed")
    reasons += [
        f"doc {doc} changed but should not have"
        for doc in before.docs
        if _doc_differs(before, after, doc)
    ]
    if after.state_hash != before.state_hash:
        reasons.append(".machi/machinate.toml changed")
    return CheckResult(passed=not reasons, reasons=reasons)


JOBS: dict[str, Job] = {
    "pick-up-work": Job(
        name="pick-up-work",
        prompts=(PICK_UP_WORK_PROMPT,),
        golden_path=(
            "task list -p auth --status todo",
            "task show -p auth 02-session-cookie",
            "task update -p auth 02-session-cookie --status in-progress",
            "edit plans/auth/tasks/02-session-cookie.md",
        ),
        checker=check_pick_up_work,
    ),
    "plan-feature": Job(
        name="plan-feature",
        prompts=(PLAN_FEATURE_PROMPT,),
        golden_path=(
            "plan add password-reset --status active",
            "context add -p password-reset decisions",
            "task add -p password-reset 01-... 02-... 03-...",
            "edit plans/password-reset/plan.md",
        ),
        checker=check_plan_feature,
    ),
    "record-doc": Job(
        name="record-doc",
        prompts=(RECORD_DOC_PROMPT,),
        golden_path=(
            "doc add secret-storage --summary 'Where application secrets are stored'",
            "edit docs/secret-storage.md",
        ),
        checker=check_record_doc,
    ),
    "recall-doc": Job(
        name="recall-doc",
        prompts=(RECALL_DOC_PROMPT,),
        golden_path=("doc list", "doc show incident-2025-03"),
        checker=check_recall_doc,
    ),
    "answer-question": Job(
        name="answer-question",
        prompts=(ANSWER_QUESTION_PROMPT,),
        golden_path=(
            "task list -p billing --status done",
            "plan list --sort last_activity_at --descending",
        ),
        checker=check_answer_question,
    ),
    "two-agents": Job(
        name="two-agents",
        prompts=TWO_AGENTS_PROMPTS,
        golden_path=(
            "task list -p auth --status todo",
            "task update -p auth 03-logout --status done",
        ),
        checker=check_two_agents,
    ),
}
