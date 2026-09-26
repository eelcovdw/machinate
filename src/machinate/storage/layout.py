from pathlib import PurePosixPath

from .models import ContextNameInput, NameInput, TaskNameInput
from .queries import DocumentCollection, DocumentScope

_PLANS_DIRECTORY = PurePosixPath("plans")


class Layout:
    def project(self) -> PurePosixPath:
        return PurePosixPath("project.md")

    def plan(self, name: str) -> PurePosixPath:
        name = NameInput(name=name).name
        return _PLANS_DIRECTORY / name / "plan.md"

    def task(self, plan: str, name: str) -> PurePosixPath:
        name = TaskNameInput(name=name).name
        return self.plan(plan).parent / "tasks" / f"{name}.md"

    def context(self, plan: str, name: str) -> PurePosixPath:
        name = ContextNameInput(name=name).name
        return self.plan(plan).parent / "context" / f"{name}.md"

    def plan_activity_scopes(self) -> tuple[DocumentScope, ...]:
        """Return scopes relative to the plan document's directory."""
        return (
            DocumentScope(path=PurePosixPath("tasks"), pattern=PurePosixPath("**/*.md")),
            DocumentScope(path=PurePosixPath("context"), pattern=PurePosixPath("**/*.md")),
        )

    def plan_collection(self) -> DocumentCollection:
        return DocumentCollection(
            path=_PLANS_DIRECTORY,
            pattern=PurePosixPath("*/plan.md"),
            name_source="parent",
            activity_scopes=self.plan_activity_scopes(),
        )

    def task_collection(self, plan: str) -> DocumentCollection:
        return DocumentCollection(
            path=self.plan(plan).parent / "tasks", pattern=PurePosixPath("**/*.md")
        )

    def context_collection(self, plan: str) -> DocumentCollection:
        return DocumentCollection(
            path=self.plan(plan).parent / "context", pattern=PurePosixPath("**/*.md")
        )
