from datetime import UTC, datetime
from pathlib import Path

import pytest

from machinate.models.doc import DocUpdate
from machinate.services.doc import DocService
from machinate.storage import DocMetadata, DocumentQuery, DocumentStore, Layout

_CREATED = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def service(tmp_path: Path) -> DocService:
    return DocService(DocumentStore(tmp_path), Layout())


def test_create_get_update_round_trip(service: DocService) -> None:
    created = service.create("topic/spec", DocMetadata(created=_CREATED), "body")
    assert created.name == "topic/spec"
    assert created.path.as_posix() == "docs/topic/spec.md"
    assert service.get("topic/spec").document.body == "body"

    updated = service.update("topic/spec", DocUpdate(summary="s", tags=["x"]))
    assert updated.document.metadata.summary == "s"
    assert updated.document.metadata.tags == ["x"]
    assert service.get("topic/spec").document.body == "body"


def test_update_with_no_fields_is_a_noop(service: DocService) -> None:
    service.create("spec", DocMetadata(created=_CREATED), "body")
    before = service.path("spec")
    service.update("spec", DocUpdate())
    assert service.get("spec").document.body == "body"
    assert service.path("spec") == before


def test_trailing_markdown_suffix_is_ignored(service: DocService) -> None:
    created = service.create("topic/spec.md", DocMetadata(created=_CREATED), "body")
    assert created.name == "topic/spec"
    assert created.path.as_posix() == "docs/topic/spec.md"
    assert service.get("topic/spec.md").name == "topic/spec"
    assert service.path("topic/spec.md").as_posix() == "docs/topic/spec.md"


def test_create_batch_reports_partial_failures(service: DocService) -> None:
    service.create("existing", DocMetadata(created=_CREATED))
    created, errors = service.create_batch(
        ["new", "existing", "../bad"], DocMetadata(created=_CREATED)
    )
    assert [doc.name for doc in created] == ["new"]
    assert [error.name for error in errors] == ["existing", "../bad"]


def test_list_filters_sorts_and_limits(service: DocService) -> None:
    service.create("b", DocMetadata(created=_CREATED, tags=["x"]))
    service.create("a", DocMetadata(created=_CREATED, tags=["y"]))
    service.create("c", DocMetadata(created=_CREATED, tags=["x"]))

    tagged = service.list(DocumentQuery(tags={"x"}))
    assert [record.name for record in tagged] == ["b", "c"]

    descending = service.list(DocumentQuery(descending=True))
    assert [record.name for record in descending] == ["c", "b", "a"]

    limited = service.list(DocumentQuery(limit=2))
    assert [record.name for record in limited] == ["a", "b"]
