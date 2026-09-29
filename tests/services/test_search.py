import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from machinate.models.documents import (
    ContextMetadata,
    Metadata,
    ParsedDocument,
    PlanMetadata,
    TaskMetadata,
)
from machinate.models.operations import FindQuery
from machinate.services.search import SearchService
from machinate.storage import DocumentStore, Layout, MissingDocumentError

_NOW = datetime(2026, 9, 22, tzinfo=UTC)


def _doc(metadata: Metadata, body: str) -> ParsedDocument[Metadata]:
    return ParsedDocument(metadata=metadata, body=body)


@pytest.fixture
def search(tmp_path: Path) -> SearchService:
    store = DocumentStore(tmp_path)
    layout = Layout()
    store.create(layout.plan("auth"), _doc(PlanMetadata(created=_NOW), "gamma plan body"))
    store.create(layout.plan("billing"), _doc(PlanMetadata(created=_NOW), "delta plan body"))
    store.create(
        layout.task("auth", "login"), _doc(TaskMetadata(created=_NOW), "kangaroo login flow")
    )
    store.create(
        layout.task("auth", "abcd/efg/h"), _doc(TaskMetadata(created=_NOW), "nested task body")
    )
    store.create(
        layout.context("auth", "oauth"),
        _doc(ContextMetadata(created=_NOW), "unicorn context notes"),
    )
    (tmp_path / "notes.txt").write_text("plain notes")
    (tmp_path / "misc").mkdir()
    (tmp_path / "misc" / "random.md").write_text("random misc")
    return SearchService(store, layout)


def paths(search: SearchService, query: FindQuery | None = None) -> list[str]:
    return [entry.path.as_posix() for entry in search.find(query)]


def test_default_listing_is_sorted_and_excludes_non_markdown(search: SearchService) -> None:
    assert paths(search, FindQuery()) == [
        "misc/random.md",
        "plans/auth/context/oauth.md",
        "plans/auth/plan.md",
        "plans/auth/tasks/abcd/efg/h.md",
        "plans/auth/tasks/login.md",
        "plans/billing/plan.md",
    ]


def test_listing_has_no_scores(search: SearchService) -> None:
    entries = search.find(FindQuery())
    assert all(entry.score is None for entry in entries)


def test_dot_prefixed_document_is_listed_and_searchable(search: SearchService) -> None:
    search.document_store.create(
        search.layout.task("auth", ".hidden"),
        _doc(TaskMetadata(created=_NOW), "quokka hidden note"),
    )
    assert "plans/auth/tasks/.hidden.md" in paths(search, FindQuery())
    assert paths(search, FindQuery(query="quokka")) == ["plans/auth/tasks/.hidden.md"]


def test_symlinked_file_is_indexed_and_dangling_symlink_is_skipped(search: SearchService) -> None:
    root = search.document_store.root
    (root / "link.md").symlink_to(root / "plans" / "auth" / "plan.md")
    (root / ".#lock.md").symlink_to(root / "missing.md")
    found = paths(search, FindQuery())
    assert "link.md" in found
    assert ".#lock.md" not in found


def test_membership_is_derived_from_path(search: SearchService) -> None:
    by_path = {entry.path.as_posix(): entry for entry in search.find(FindQuery())}
    assert (by_path["plans/auth/plan.md"].kind, by_path["plans/auth/plan.md"].name) == (
        "plan",
        "auth",
    )
    nested = by_path["plans/auth/tasks/abcd/efg/h.md"]
    assert (nested.kind, nested.plan, nested.name) == ("task", "auth", "abcd/efg/h")
    context = by_path["plans/auth/context/oauth.md"]
    assert (context.kind, context.plan, context.name) == ("context", "auth", "oauth")
    assert by_path["misc/random.md"].kind == "unknown"
    assert by_path["misc/random.md"].plan is None


def test_single_star_does_not_cross_slash(search: SearchService) -> None:
    assert paths(search, FindQuery(globs=["plans/*/*.md"])) == [
        "plans/auth/plan.md",
        "plans/billing/plan.md",
    ]


def test_multiple_patterns_are_an_or(search: SearchService) -> None:
    assert paths(search, FindQuery(globs=["plans/*/tasks/*.md", "plans/*/context/*.md"])) == [
        "plans/auth/context/oauth.md",
        "plans/auth/tasks/login.md",
    ]


def test_explicit_pattern_selects_other_extensions(search: SearchService) -> None:
    assert paths(search, FindQuery(globs=["**/*.txt"])) == ["notes.txt"]


def test_content_match_returns_file(search: SearchService) -> None:
    result = paths(search, FindQuery(query="kangaroo"))
    assert result == ["plans/auth/tasks/login.md"]


def test_short_prefix_query_matches_tokens(search: SearchService) -> None:
    # Fuzzy matching treats a term as a prefix: "kang" finds the "kangaroo" token.
    assert paths(search, FindQuery(query="kang")) == ["plans/auth/tasks/login.md"]


def test_exact_disables_prefix_and_typo_matching(search: SearchService) -> None:
    assert paths(search, FindQuery(query="kang", exact=True)) == []


def test_short_body_tokens_do_not_false_positive(search: SearchService) -> None:
    # "auth" is a path token; editing it into "authoring" is beyond the fuzzy distance.
    assert paths(search, FindQuery(query="authoring")) == []


def test_edit_similarity_is_discounted(search: SearchService) -> None:
    # A coincidental overlap ("author" vs "auto") must not match at distance one.
    auto = search.document_store.root / "auto.md"
    auto.write_text("auto store")
    assert "auto.md" not in paths(search, FindQuery(query="author"))


def test_multi_word_query_matches_scattered_terms(search: SearchService) -> None:
    # "login" is a path token while "kangaroo" only appears in the body.
    assert paths(search, FindQuery(query="kangaroo login")) == ["plans/auth/tasks/login.md"]


def test_regex_needs_opt_in_and_a_field(search: SearchService) -> None:
    assert paths(search, FindQuery(query="path:/.*oauth.*/", regex=True)) == [
        "plans/auth/context/oauth.md"
    ]
    with pytest.raises(ValueError, match="Regex"):
        search.find(FindQuery(query="path:/.*oauth.*/"))


def test_limit_applies_after_ranking(search: SearchService) -> None:
    assert len(search.find(FindQuery(query="plan", limit=2))) == 2
    assert paths(search, FindQuery(limit=1)) == ["misc/random.md"]


def test_plan_scope_narrows_results(search: SearchService) -> None:
    entries = search.find(FindQuery(plan="auth"))
    assert entries
    assert all(entry.plan == "auth" for entry in entries)
    assert all(entry.path.as_posix().startswith("plans/auth/") for entry in entries)


def test_missing_plan_raises(search: SearchService) -> None:
    with pytest.raises(MissingDocumentError):
        search.find(FindQuery(plan="nope"))


def test_malformed_frontmatter_does_not_raise(search: SearchService) -> None:
    broken = search.document_store.root / "broken.md"
    broken.write_text("---\ncreated: [unterminated\n---\nbody zebra text\n")
    result = paths(search, FindQuery(query="zebra"))
    assert "broken.md" in result


def test_invalid_utf8_does_not_raise(search: SearchService) -> None:
    broken = search.document_store.root / "binary.md"
    broken.write_bytes(b"\xff\xfe\x00bad")
    assert "binary.md" in paths(search)


def test_unreadable_document_is_reported_and_still_path_searchable(
    search: SearchService, caplog: pytest.LogCaptureFixture
) -> None:
    broken = search.document_store.root / "binary.md"
    broken.write_bytes(b"\xff\xfe\x00bad")
    with caplog.at_level(logging.WARNING):
        result = paths(search, FindQuery(query="binary"))
    assert result == ["binary.md"]  # Path text is indexed even when the body cannot be read.
    assert "binary.md" in caplog.text


def test_frontmatter_is_indexed(search: SearchService) -> None:
    tagged = search.document_store.root / "tagged.md"
    tagged.write_text("---\nsummary: aardvark\n---\nplain body\n")
    assert "tagged.md" in paths(search, FindQuery(query="aardvark"))
    assert "tagged.md" in paths(search, FindQuery(query="plain body"))


@pytest.mark.parametrize("globs", [["../*.md"], ["/etc/*.md"], ["a\\b"], [""]])
def test_find_query_rejects_escaping_globs(globs: list[str]) -> None:
    with pytest.raises(ValidationError):
        FindQuery(globs=globs)
