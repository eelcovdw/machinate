import unicodedata
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from machinate.models.documents import (
    NAME_ADAPTER,
    NESTED_NAME_ADAPTER,
    PlanMetadata,
)


@pytest.mark.parametrize(
    "name",
    ["", " ", ".", "..", ".hidden", "../escape", "a/.hidden", "a/b", "a\\b", "C:drive", "bad\n"],
)
def test_names_reject_invalid_values(name: str) -> None:
    with pytest.raises(ValidationError):
        NAME_ADAPTER.validate_python(name)
    if name == "a/b":
        assert NESTED_NAME_ADAPTER.validate_python(name) == "a/b"
    else:
        with pytest.raises(ValidationError):
            NESTED_NAME_ADAPTER.validate_python(name)


def test_names_are_normalized_to_nfc() -> None:
    decomposed = "Cafe\u0301"
    composed = unicodedata.normalize("NFC", decomposed)
    assert composed != decomposed
    assert NAME_ADAPTER.validate_python(decomposed) == composed
    assert NESTED_NAME_ADAPTER.validate_python(f"topic/{decomposed}.md") == f"topic/{composed}"


@pytest.mark.parametrize(
    ("adapter", "name", "expected"),
    [
        (NAME_ADAPTER, "spec.md", "spec"),
        (NAME_ADAPTER, "Spec.MD", "Spec"),
        (NESTED_NAME_ADAPTER, "topic/spec.md", "topic/spec"),
    ],
)
def test_names_ignore_markdown_suffix(adapter: TypeAdapter[str], name: str, expected: str) -> None:
    assert adapter.validate_python(name) == expected


def test_tag_validation_and_deduplication() -> None:
    metadata = PlanMetadata(
        created_at=datetime(2026, 9, 22, tzinfo=UTC), tags=[" A ", "a", "b", "A"]
    )
    assert metadata.tags == ["A", "b"]
    for invalid in ("", "   ", "bad\x01"):
        with pytest.raises(ValidationError):
            PlanMetadata(created_at=datetime(2026, 9, 22, tzinfo=UTC), tags=[invalid])
