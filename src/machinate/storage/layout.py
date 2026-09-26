from pathlib import PurePosixPath

from .models import ContextNameInput, NameInput, TaskNameInput
from .queries import DocumentCollection, DocumentScope


class Layout:
    def project(self) -> PurePosixPath:
        return PurePosixPath("project.md")

    def plan(self, name: str) -> PurePosixPath:
        name = NameInput(name=name).name
        return PurePosixPath(name, "plan.md")

    def task(self, plan: str, name: str) -> PurePosixPath:
        plan = NameInput(name=plan).name
        name = TaskNameInput(name=name).name
        return PurePosixPath(plan, "tasks", f"{name}.md")

    def context(self, plan: str, name: str) -> PurePosixPath:
        plan = NameInput(name=plan).name
        name = ContextNameInput(name=name).name
        return PurePosixPath(plan, "context", f"{name}.md")

    def plan_activity_scopes(self) -> tuple[DocumentScope, ...]:
        """Return scopes relative to the plan document's directory."""
        return (
            DocumentScope(path=PurePosixPath("tasks"), pattern=PurePosixPath("**/*.md")),
            DocumentScope(path=PurePosixPath("context"), pattern=PurePosixPath("**/*.md")),
        )

    def plan_collection(self) -> DocumentCollection:
        return DocumentCollection(
            path=PurePosixPath("."),
            pattern=PurePosixPath("*/plan.md"),
            name_source="parent",
            activity_scopes=self.plan_activity_scopes(),
        )

    def task_collection(self, plan: str) -> DocumentCollection:
        plan = NameInput(name=plan).name
        return DocumentCollection(
            path=PurePosixPath(plan, "tasks"), pattern=PurePosixPath("**/*.md")
        )

    def context_collection(self, plan: str) -> DocumentCollection:
        plan = NameInput(name=plan).name
        return DocumentCollection(
            path=PurePosixPath(plan, "context"), pattern=PurePosixPath("**/*.md")
        )
