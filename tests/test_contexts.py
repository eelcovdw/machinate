import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import override

import pytest
from pydantic import ValidationError
from upath import UPath

from machinate.models.context import Context, ContextUpdate
from machinate.services.context import ContextService
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentCollection,
    DocumentExistsError,
    DocumentStore,
    Layout,
    PlanMetadata,
)
from machinate.storage.models import ContextNameInput, NameInput


@pytest.fixture
def service(tmp_path: Path) -> ContextService:
    store = DocumentStore(UPath(tmp_path / "docs"))
    store.create(
        Layout().plan("alpha"),
        Document(metadata=PlanMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body=""),
    )
    return ContextService(store, Layout())


@pytest.fixture
def metadata() -> ContextMetadata:
    return ContextMetadata.model_validate(
        {
            "created": "2026-09-22T12:34:56.123456+02:00",
            "custom": {"owner": "Alice"},
            "status": "custom status",
        }
    )


def test_create_get_duplicates_and_exact_names(
    service: ContextService, metadata: ContextMetadata
) -> None:
    context = service.create("alpha", "research", metadata, "Body\n")
    assert context == service.get("alpha", "research")
    assert context.path == PurePosixPath("plans/alpha/context/research.md")
    assert context.document == Document(metadata=metadata, body="Body\n")
    assert json.loads(context.model_dump_json())["path"] == "plans/alpha/context/research.md"
    assert Context.model_validate(json.loads(context.model_dump_json())) == context
    with pytest.raises(DocumentExistsError):
        service.create("alpha", "research", metadata, "Replacement")
    assert service.get("alpha", "research") == context


@pytest.mark.parametrize(
    "patch",
    [{"status": "done"}, {"body": None}, {"created": "2026-01-01T00:00:00Z"}, {"unknown": 1}],
)
def test_patch_validation(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ContextUpdate.model_validate(patch)


def test_method_validation(service: ContextService, metadata: ContextMetadata) -> None:
    for operation in (
        lambda: service.create("../bad", "research", metadata),
        lambda: service.get("../bad", "research"),
        lambda: service.update("../bad", "research", ContextUpdate()),
        lambda: service.list("../bad"),
    ):
        with pytest.raises(ValidationError):
            operation()
    with pytest.raises(ValidationError):
        service.create("alpha", "research", {"summary": "missing date"})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.create("alpha", "research", {"created": "2026-09-22T12:00:00"})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.create("alpha", "research", metadata, None)  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.update("alpha", "research", {"body": None})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.list("alpha", {"limit": 0})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.list("alpha", {"statuses": ["done"]})  # pyright: ignore[reportArgumentType]


class AlternateLayout(Layout):
    @override
    def plan(self, name: str) -> PurePosixPath:
        return PurePosixPath("registry", NameInput(name=name).name, "index.md")

    @override
    def context(self, plan: str, name: str) -> PurePosixPath:
        return PurePosixPath(
            "registry",
            NameInput(name=plan).name,
            "notes",
            f"{ContextNameInput(name=name).name}.note",
        )

    @override
    def context_collection(self, plan: str) -> DocumentCollection:
        return DocumentCollection(
            path=PurePosixPath("registry", NameInput(name=plan).name, "notes"),
            pattern=PurePosixPath("**/*.note"),
        )


def test_layout_controls_lookup_and_discovery(
    service: ContextService, metadata: ContextMetadata
) -> None:
    layout = AlternateLayout()
    service.document_store.create(
        layout.plan("alpha"),
        Document(metadata=PlanMetadata(created=metadata.created), body=""),
    )
    alternate = ContextService(service.document_store, layout)
    service.create("alpha", "ignored", metadata)
    context = alternate.create("alpha", "nested/research", metadata, "Body")
    assert context.path == PurePosixPath("registry/alpha/notes/nested/research.note")
    assert [summary.name for summary in alternate.list("alpha")] == ["nested/research"]
    assert alternate.get("alpha", "nested/research") == context
    assert (
        alternate.update("alpha", "nested/research", ContextUpdate(body="Changed")).document.body
        == "Changed"
    )
