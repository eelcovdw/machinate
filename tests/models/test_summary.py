from datetime import UTC, datetime
from pathlib import Path

from machinate.models.documents import ContextMetadata, ParsedDocument, derive_summary
from machinate.storage import DocumentStore


def test_no_prose_returns_none() -> None:
    assert derive_summary("") is None
    assert derive_summary("\n\n") is None
    assert derive_summary("# Title\n\n## Section\n\n") is None


def test_first_paragraph_is_summary() -> None:
    assert derive_summary("# Plan: auth\n\nClose the gap.\n\nMore detail.") == "Close the gap."


def test_heading_paragraph_before_prose() -> None:
    assert derive_summary("## What\n\nText.") == "Text."


def test_label_preamble_is_skipped() -> None:
    assert derive_summary("Project: machinate\n\nDo the thing.") == "Do the thing."
    assert derive_summary("# Plan: x\nProject: y\n\nDo the thing.") == "Do the thing."


def test_markdown_is_stripped() -> None:
    body = "Use `machi` with **bold** and [a link](https://example.com) here."
    assert derive_summary(body) == "Use machi with bold and a link here."


def test_multiline_paragraph_is_joined() -> None:
    assert derive_summary("First line\nsecond line\n\nNext.") == "First line second line"


def test_fenced_code_is_skipped() -> None:
    assert derive_summary("```python\nx = 1\n```\n\nReal prose.") == "Real prose."
    assert derive_summary("```\ncode\n```") is None


def test_lone_label_line_is_kept() -> None:
    # A body that is only a label has no prose to fall back to, so keep the label.
    assert derive_summary("TODO: fix the race in write.") == "TODO: fix the race in write."
    assert derive_summary("Intro.\n\nTODO: fix the race in write.") == "Intro."


def test_stored_summary_wins_over_derived(tmp_path: Path) -> None:
    """A stored summary is persisted and preferred; an unset one stays out of the file."""
    store = DocumentStore(tmp_path)
    store.create(
        "note.md",
        ParsedDocument(
            metadata=ContextMetadata(created_at=datetime(2026, 1, 1, tzinfo=UTC)), body="Hello"
        ),
    )
    assert "summary" not in (tmp_path / "note.md").read_text()
    document = store.read("note.md", ContextMetadata)
    assert document.determine_summary() == "Hello"

    (tmp_path / "stored.md").write_text(
        "---\ncreated_at: 2026-01-01T00:00:00Z\nsummary: Curated\n---\nBody paragraph.\n"
    )
    document = store.read("stored.md", ContextMetadata)
    assert document.metadata.summary == "Curated"
    assert document.determine_summary() == "Curated"

    store.create(
        "authored.md",
        ParsedDocument(
            metadata=ContextMetadata(
                created_at=datetime(2026, 1, 1, tzinfo=UTC), summary="Curated"
            ),
            body="Body paragraph.",
        ),
    )
    assert "summary: Curated" in (tmp_path / "authored.md").read_text()
    assert store.read("authored.md", ContextMetadata).metadata.summary == "Curated"
