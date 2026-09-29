import logging
from pathlib import PurePosixPath
from typing import cast

import tantivy
from pydantic import validate_call

from machinate.models.documents import PlanMetadata
from machinate.models.operations import DEFAULT_GLOB, FindEntry, FindQuery
from machinate.storage import DocumentStore, Layout, StorageError

logger = logging.getLogger(__name__)

_TEXT_FIELDS = ("path", "body")
_PATH_BOOST = 2.0
_FUZZY_FIELD = (True, 1, True)


def _doc_id(searcher: tantivy.Searcher, address: tantivy.DocAddress) -> int:
    """Read back the stored document id used as the position in the candidate list."""
    return cast("int", searcher.doc(address)["doc_id"][0])


class SearchService:
    """Glob a project's documents and rank query matches with an ad-hoc tantivy index.

    The index is built in memory on each query run and discarded afterwards: at a few
    thousand documents that costs ~100 ms, which is cheaper than persisting and
    invalidating an index on disk. A glob-only listing builds no index at all.
    """

    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    @validate_call
    def find(self, query: FindQuery | None = None) -> list[FindEntry]:
        query = query or FindQuery()
        base = PurePosixPath()
        if query.plan is not None:
            plan_path = self.layout.plan(query.plan)
            self.document_store.read(plan_path, PlanMetadata)
            base = plan_path.parent

        relatives = self.document_store.glob_files(base, query.globs or [DEFAULT_GLOB])
        text = (query.query or "").strip()
        if text:
            entries = self._rank(query, text, relatives)
        else:
            entries = sorted(
                (self._entry(relative, None) for relative in relatives),
                key=lambda entry: entry.path.as_posix(),
            )
        return entries[: query.limit] if query.limit is not None else entries

    def _rank(self, query: FindQuery, text: str, relatives: list[PurePosixPath]) -> list[FindEntry]:
        if not relatives:
            return []
        index = self._build(relatives)
        searcher = index.searcher()
        if query.exact:
            parsed = index.parse_query(
                text,
                default_field_names=list(_TEXT_FIELDS),
                field_boosts={"path": _PATH_BOOST},
                allow_regexes=query.regex,
            )
        else:
            parsed = index.parse_query(
                text,
                default_field_names=list(_TEXT_FIELDS),
                field_boosts={"path": _PATH_BOOST},
                fuzzy_fields=dict.fromkeys(_TEXT_FIELDS, _FUZZY_FIELD),
                allow_regexes=query.regex,
            )
        hits = cast(
            "list[tuple[float, tantivy.DocAddress]]",
            searcher.search(parsed, len(relatives)).hits,
        )
        if query.limit is not None:
            hits = hits[: query.limit]
        entries: list[FindEntry] = []
        for score, address in hits:
            relative = relatives[_doc_id(searcher, address)]
            entries.append(self._entry(relative, score))
        return entries

    def _build(self, relatives: list[PurePosixPath]) -> tantivy.Index:
        builder = tantivy.SchemaBuilder()
        builder.add_text_field("path", stored=False)
        builder.add_text_field("body", stored=False)
        builder.add_integer_field("doc_id", stored=True)
        index = tantivy.Index(builder.build())
        writer = index.writer()
        for doc_id, relative in enumerate(relatives):
            writer.add_document(
                tantivy.Document(
                    path=relative.as_posix(), body=self._read_text(relative), doc_id=doc_id
                )
            )
        writer.commit()
        index.reload()
        return index

    def _entry(self, relative: PurePosixPath, score: float | None) -> FindEntry:
        membership = self.layout.resolve(relative)
        return FindEntry(
            path=relative,
            kind=membership.kind,
            plan=membership.plan,
            name=membership.name,
            score=score,
        )

    def _read_text(self, relative: PurePosixPath) -> str:
        """Raw text for indexing; unreadable files are reported and indexed by path only."""
        try:
            return self.document_store.read_text(relative)
        except StorageError as exc:
            logger.warning("Unreadable document body skipped: %s", exc)
            return ""
