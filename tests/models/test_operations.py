"""Update models re-validate the metadata they produce and reject an explicit null status."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from machinate.models.documents import ParsedDocument, TaskMetadata, TaskStatus
from machinate.models.operations import StatusUpdate


def _document(tags: list[str]) -> ParsedDocument[TaskMetadata]:
    metadata = TaskMetadata.model_validate(
        {"created_at": datetime(2026, 9, 22, tzinfo=UTC), "tags": tags}
    )
    return ParsedDocument(metadata=metadata, body="")


def test_tag_update_revalidates_merged_metadata() -> None:
    updated = StatusUpdate[TaskStatus](tags=["A", "a"]).apply_to(_document(["A"]))
    assert updated is not None
    assert updated.metadata.tags == ["A"]


def test_explicit_null_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StatusUpdate[TaskStatus](status=None)
    with pytest.raises(ValidationError):
        StatusUpdate[TaskStatus].model_validate({"status": None})
