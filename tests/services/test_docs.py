from pathlib import Path

import pytest

from machinate.models.operations import CreateInput, DocumentQuery, DocUpdate
from machinate.services.doc import DocService
from machinate.storage import DocumentStore, Layout


@pytest.fixture
def service(tmp_path: Path) -> DocService:
    return DocService(DocumentStore(tmp_path), Layout())


def test_create_get_update_round_trip(service: DocService) -> None:
    created = service.create("topic/spec", CreateInput(), "body")
    assert created.record.name == "topic/spec"
    assert created.record.path.as_posix() == "docs/topic/spec.md"
    assert service.get("topic/spec").body == "body"

    updated = service.update("topic/spec", DocUpdate(summary="s", tags=["x"]))
    assert updated.record.metadata.summary == "s"
    assert updated.record.metadata.tags == ["x"]
    assert service.get("topic/spec").body == "body"


def test_update_with_no_fields_is_a_noop(service: DocService) -> None:
    service.create("spec", CreateInput(), "body")
    before = service.path("spec")
    service.update("spec", DocUpdate())
    assert service.get("spec").body == "body"
    assert service.path("spec") == before


def test_trailing_markdown_suffix_is_ignored(service: DocService) -> None:
    created = service.create("topic/spec.md", CreateInput(), "body")
    assert created.record.name == "topic/spec"
    assert created.record.path.as_posix() == "docs/topic/spec.md"
    assert service.get("topic/spec.md").record.name == "topic/spec"
    assert service.path("topic/spec.md").as_posix() == "docs/topic/spec.md"


def test_create_batch_reports_partial_failures(service: DocService) -> None:
    service.create("existing", CreateInput())
    created, errors = service.create_batch(["new", "existing", "../bad"], CreateInput())
    assert [doc.record.name for doc in created] == ["new"]
    assert [error.name for error in errors] == ["existing", "../bad"]


def test_list_filters_sorts_and_limits(service: DocService) -> None:
    service.create("b", CreateInput(tags=["x"]))
    service.create("a", CreateInput(tags=["y"]))
    service.create("c", CreateInput(tags=["x"]))

    tagged = service.list(DocumentQuery(tags={"x"}))
    assert [record.name for record in tagged] == ["b", "c"]

    descending = service.list(DocumentQuery(descending=True))
    assert [record.name for record in descending] == ["c", "b", "a"]

    limited = service.list(DocumentQuery(limit=2))
    assert [record.name for record in limited] == ["a", "b"]
