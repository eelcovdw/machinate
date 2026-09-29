import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from machinate.models.documents import ParsedDocument, PlanMetadata
from machinate.models.operations import CreateInput
from machinate.services.context import ContextService
from machinate.storage import DocumentExistsError, DocumentStore, Layout


@pytest.fixture
def service(tmp_path: Path) -> ContextService:
    store = DocumentStore(tmp_path / "docs")
    store.create(
        Layout().plan("alpha"),
        ParsedDocument(
            metadata=PlanMetadata(created_at=datetime(2026, 9, 22, tzinfo=UTC)), body=""
        ),
    )
    return ContextService(store, Layout())


def test_create_get_duplicates_and_exact_names(service: ContextService) -> None:
    create = CreateInput(summary="Research", tags=["auth"])
    context = service.create("alpha", "research", create, "Body\n")
    assert context == service.get("alpha", "research")
    assert context.record.path == PurePosixPath("plans/alpha/context/research.md")
    assert context.body == "Body\n"
    assert context.record.metadata.summary == "Research"
    assert context.record.metadata.tags == ["auth"]
    assert context.record.metadata.created_at.tzinfo is not None
    assert json.loads(context.record.model_dump_json())["path"] == "plans/alpha/context/research.md"
    assert (
        type(context.record)
        .model_validate(json.loads(context.record.model_dump_json()))
        .model_dump()
        == context.record.model_dump()
    )
    with pytest.raises(DocumentExistsError):
        service.create("alpha", "research", CreateInput(), "Replacement")
    assert service.get("alpha", "research") == context
