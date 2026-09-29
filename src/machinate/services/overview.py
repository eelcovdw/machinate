"""Plan and project overviews, built from the resource services."""

from typing import cast, get_args

from machinate.models.documents import Name, PlanStatus, TaskStatus
from machinate.models.operations import PlanOverview, ProjectOverview
from machinate.services.context import ContextService
from machinate.services.doc import DocService
from machinate.services.plan import PlanService
from machinate.services.task import TaskService

# The status literals, read from the type aliases so adding a status needs no other edit.
_PLAN_STATUSES = cast("tuple[PlanStatus, ...]", get_args(PlanStatus.__value__))  # pyright: ignore[reportAny]
_TASK_STATUSES = cast("tuple[TaskStatus, ...]", get_args(TaskStatus.__value__))  # pyright: ignore[reportAny]


class OverviewService:
    def __init__(
        self,
        plans: PlanService,
        tasks: TaskService,
        contexts: ContextService,
        docs: DocService,
    ) -> None:
        self.plans: PlanService = plans
        self.tasks: TaskService = tasks
        self.contexts: ContextService = contexts
        self.docs: DocService = docs

    def _tasks_by_status(self, plan: Name) -> dict[TaskStatus, int]:
        counts: dict[TaskStatus, int] = dict.fromkeys(_TASK_STATUSES, 0)
        for task in self.tasks.list_records(plan):
            counts[task.metadata.status] += 1
        return counts

    def plan_overview(self, plan: Name) -> PlanOverview:
        loaded = self.plans.get(plan)
        return PlanOverview(
            current=self.plans.current_name() == plan,
            plan=loaded.record,
            tasks_by_status=self._tasks_by_status(plan),
            context_count=self.contexts.count_documents(plan),
        )

    def project_overview(self) -> ProjectOverview:
        plans = self.plans.list_records()
        plans_by_status: dict[PlanStatus, int] = dict.fromkeys(_PLAN_STATUSES, 0)
        tasks_by_status: dict[TaskStatus, int] = dict.fromkeys(_TASK_STATUSES, 0)
        context_count = 0
        for plan in plans:
            plans_by_status[plan.metadata.status] += 1
            context_count += self.contexts.count_documents(plan.name)
            for status, count in self._tasks_by_status(plan.name).items():
                tasks_by_status[status] += count
        current = self.plans.current_name()
        names = {plan.name for plan in plans}
        return ProjectOverview(
            current_plan=current,
            selection_valid=current is None or current in names,
            plan_count=len(plans),
            plans_by_status=plans_by_status,
            tasks_by_status=tasks_by_status,
            context_count=context_count,
            doc_count=self.docs.count_documents(),
            recent_plans=sorted(plans, key=lambda plan: plan.last_activity_at, reverse=True)[:5],
        )
