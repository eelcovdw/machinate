import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from machinate.models.context import Context
from machinate.services.context import ContextService
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentExistsError,
    DocumentStore,
    Layout,
    PlanMetadata,
)


@pytest.fixture
def service(tmp_path: Path) -> ContextService:
    store = DocumentStore(tmp_path / "docs")
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
