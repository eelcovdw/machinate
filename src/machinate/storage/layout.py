from pathlib import PurePosixPath

from machinate.models.documents import DocumentKind, DocumentMembership, Name, NestedName

from .models import DocumentCollection, DocumentScope

_PLANS_DIRECTORY = PurePosixPath("plans")
_TASKS_DIRECTORY = PurePosixPath("tasks")
_CONTEXT_DIRECTORY = PurePosixPath("context")
_DOCS_DIRECTORY = PurePosixPath("docs")
_PLAN_DOCUMENT = PurePosixPath("plan.md")

_COLLECTION_KINDS: dict[str, DocumentKind] = {
    _TASKS_DIRECTORY.name: "task",
    _CONTEXT_DIRECTORY.name: "context",
}


class Layout:
    def plan(self, name: Name) -> PurePosixPath:
        return _PLANS_DIRECTORY / name / _PLAN_DOCUMENT

    def task(self, plan: Name, name: NestedName) -> PurePosixPath:
        return self.plan(plan).parent / _TASKS_DIRECTORY / f"{name}.md"

    def context(self, plan: Name, name: NestedName) -> PurePosixPath:
        return self.plan(plan).parent / _CONTEXT_DIRECTORY / f"{name}.md"

    def doc(self, name: NestedName) -> PurePosixPath:
        return _DOCS_DIRECTORY / f"{name}.md"

    def resolve(self, path: PurePosixPath) -> DocumentMembership:
        """Reverse a store-relative path to its kind and owning plan/name.

        Mirrors the forward conventions: plans live at ``plans/{plan}/plan.md`` and are
        flat, while tasks and context may be nested and keep their collection-relative
        directory path as the name. Project docs live at ``docs/{name}.md`` and may be
        nested, with no owning plan.
        """
        parts = path.parts
        if parts[:1] == (_DOCS_DIRECTORY.name,) and len(parts) > 1 and path.suffix == ".md":
            name = PurePosixPath(*parts[1:]).with_suffix("").as_posix()
            return DocumentMembership(kind="doc", name=name)
        if parts[:1] != (_PLANS_DIRECTORY.name,):
            return DocumentMembership(kind="unknown")

        rest = parts[1:]
        if not rest:
            return DocumentMembership(kind="unknown")

        plan, *tail = rest
        if tail == [_PLAN_DOCUMENT.name]:
            return DocumentMembership(kind="plan", plan_name=plan, name=plan)

        kind = _COLLECTION_KINDS.get(tail[0]) if tail else None
        if kind is not None and path.suffix == ".md":
            name_parts = tail[1:]
            if name_parts:
                name = PurePosixPath(*name_parts).with_suffix("").as_posix()
                return DocumentMembership(kind=kind, plan_name=plan, name=name)

        return DocumentMembership(kind="unknown")

    def plan_collection(self) -> DocumentCollection:
        # Activity scopes are relative to each plan document's directory.
        return DocumentCollection(
            path=_PLANS_DIRECTORY,
            pattern=PurePosixPath("*/plan.md"),
            name_source="parent",
            activity_scopes=(
                DocumentScope(path=_TASKS_DIRECTORY, pattern=PurePosixPath("**/*.md")),
                DocumentScope(path=_CONTEXT_DIRECTORY, pattern=PurePosixPath("**/*.md")),
            ),
        )

    def task_collection(self, plan: Name) -> DocumentCollection:
        return DocumentCollection(
            path=self.plan(plan).parent / _TASKS_DIRECTORY, pattern=PurePosixPath("**/*.md")
        )

    def context_collection(self, plan: Name) -> DocumentCollection:
        return DocumentCollection(
            path=self.plan(plan).parent / _CONTEXT_DIRECTORY, pattern=PurePosixPath("**/*.md")
        )

    def docs_collection(self) -> DocumentCollection:
        return DocumentCollection(path=_DOCS_DIRECTORY, pattern=PurePosixPath("**/*.md"))
