import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from machinate.models.documents import ContextMetadata, DocumentRecord, ParsedDocument, PlanMetadata
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
    context = service.create("alpha", "research", create)
    service.document_store.write(
        service.path("alpha", "research"),
        ParsedDocument(metadata=context.record.metadata, body="Body\n"),
    )
    context = service.get("alpha", "research")
    assert context.record.path == PurePosixPath("plans/alpha/context/research.md")
    assert context.body == "Body\n"
    assert context.record.metadata.summary == "Research"
    assert context.record.metadata.tags == ["auth"]
    assert context.record.metadata.created_at.tzinfo is not None
    assert json.loads(context.record.model_dump_json())["path"] == "plans/alpha/context/research.md"
    round_tripped = DocumentRecord[ContextMetadata].model_validate_json(
        context.record.model_dump_json()
    )
    assert round_tripped.model_dump(mode="json") == context.record.model_dump(mode="json")
    with pytest.raises(DocumentExistsError):
        service.create("alpha", "research", CreateInput())
    assert service.get("alpha", "research") == context
