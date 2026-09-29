import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from machinate.models.documents import Context, ParsedDocument, PlanMetadata
from machinate.models.operations import CreateInput
from machinate.services.context import ContextService
from machinate.storage import DocumentExistsError, DocumentStore, Layout


@pytest.fixture
def service(tmp_path: Path) -> ContextService:
    store = DocumentStore(tmp_path / "docs")
    store.create(
        Layout().plan("alpha"),
        ParsedDocument(metadata=PlanMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body=""),
    )
    return ContextService(store, Layout())


def test_create_get_duplicates_and_exact_names(service: ContextService) -> None:
    create = CreateInput(summary="Research", tags=["auth"])
    context = service.create("alpha", "research", create, "Body\n")
    assert context == service.get("alpha", "research")
    assert context.path == PurePosixPath("plans/alpha/context/research.md")
    assert context.document.body == "Body\n"
    assert context.document.metadata.summary == "Research"
    assert context.document.metadata.tags == ["auth"]
    assert context.document.metadata.created.tzinfo is not None
    assert json.loads(context.model_dump_json())["path"] == "plans/alpha/context/research.md"
    assert Context.model_validate(json.loads(context.model_dump_json())) == context
    with pytest.raises(DocumentExistsError):
        service.create("alpha", "research", CreateInput(), "Replacement")
    assert service.get("alpha", "research") == context
