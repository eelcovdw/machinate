"""Plan and project overviews, built from the resource services."""

from machinate.models.documents import (
    PLAN_STATUSES,
    TASK_STATUSES,
    Name,
    PlanStatus,
    TaskStatus,
)
from machinate.models.operations import PlanOverview, ProjectOverview
from machinate.services.context import ContextService
from machinate.services.doc import DocService
from machinate.services.plan import PlanService
from machinate.services.task import TaskService

# The status literals, read once next to their definitions.


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
        counts: dict[TaskStatus, int] = dict.fromkeys(TASK_STATUSES, 0)
        for task in self.tasks.list_records(plan):
            counts[task.metadata.status] += 1
        return counts

    def get_plan_overview(self, plan: Name) -> PlanOverview:
        record = self.plans.get_record(plan)
        return PlanOverview(
            is_current=self.plans.find_current_plan() == plan,
            plan=record,
            tasks_by_status=self._tasks_by_status(plan),
            context_count=self.contexts.count_documents(plan),
        )

    def get_project_overview(self) -> ProjectOverview:
        plans = self.plans.list_records()
        plans_by_status: dict[PlanStatus, int] = dict.fromkeys(PLAN_STATUSES, 0)
        tasks_by_status: dict[TaskStatus, int] = dict.fromkeys(TASK_STATUSES, 0)
        context_count = 0
        for plan in plans:
            plans_by_status[plan.metadata.status] += 1
            context_count += self.contexts.count_documents(plan.name)
            for status, count in self._tasks_by_status(plan.name).items():
                tasks_by_status[status] += count
        current = self.plans.find_current_plan()
        names = {plan.name for plan in plans}
        return ProjectOverview(
            current_plan=current,
            current_plan_exists=None if current is None else current in names,
            plan_count=len(plans),
            plans_by_status=plans_by_status,
            tasks_by_status=tasks_by_status,
            context_count=context_count,
            doc_count=self.docs.count_documents(),
            recent_plans=sorted(plans, key=lambda plan: plan.last_activity_at, reverse=True)[:5],
        )
