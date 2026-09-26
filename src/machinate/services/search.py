import re
from pathlib import PurePosixPath
from typing import cast

import tantivy
from pydantic import validate_call
from wcmatch import glob as wcglob

from machinate.models.search import DEFAULT_GLOB, FindEntry, FindQuery, FindSnippet
from machinate.storage import DocumentStore, Layout, PlanMetadata

_TEXT_FIELDS = ("path", "body")
_PATH_BOOST = 2.0
_FUZZY_FIELD = (True, 1, True)


def _byte_to_char(text: str, byte_offset: int) -> int:
    """Map a UTF-8 byte offset to a character offset (tantivy highlight ranges are bytes)."""
    return len(text.encode("utf-8")[:byte_offset].decode("utf-8", errors="ignore"))


_TERM_SPLIT = re.compile(r"[^0-9a-z_]+")
_QUERY_FIELD = re.compile(r"[0-9a-z_]+\s*:")
_QUERY_STOPWORDS = frozenset({"and", "or", "not", "in", "to"})


def _query_terms(text: str) -> list[str]:
    """Best-effort plain terms from a tantivy query, for scanning a document by hand."""
    cleaned = _QUERY_FIELD.sub(" ", text.lower())
    return [term for term in _TERM_SPLIT.split(cleaned) if term and term not in _QUERY_STOPWORDS]


def _within_one(left: str, right: str) -> bool:
    """True when two tokens are at most one insert/delete/substitute apart."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) < len(right):
        left, right = right, left
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True)) <= 1
    index = 0
    while index < len(right) and left[index] == right[index]:
        index += 1
    return left[index + 1 :] == right[index:]


def _match_quality(term: str, token: str, *, fuzzy: bool) -> int:
    """Rank how well a token matches a term, mirroring tantivy's ``(fuzzy, 1, prefix)`` rule.

    The query is compared against the token's leading ``len(term)`` characters, so a typo in
    that prefix still matches (``cli`` -> ``clean``) and a shorter token compares whole. An
    exact hit outranks a prefix hit, which outranks a typo, so snippet selection prefers the
    strongest line.
    """
    if token == term:
        return 3
    if not fuzzy:
        return 0
    if token.startswith(term):
        return 2
    if _within_one(term, token[: len(term)]):
        return 1
    return 0


def _located_spans(line: str, terms: list[str], *, fuzzy: bool) -> list[tuple[int, int, int]]:
    """Spans of ``line`` that a query term matches, each with its match quality."""
    spans: list[tuple[int, int, int]] = []
    for match in re.finditer(r"[0-9A-Za-z_]+", line):
        token = match.group().lower()
        quality = max((_match_quality(term, token, fuzzy=fuzzy) for term in terms), default=0)
        if quality:
            spans.append((match.start(), match.end(), quality))
    return spans


def _snippet_model(
    lines: list[str],
    starts: list[int],
    window: tuple[int, int],
    context: int,
    spans: list[tuple[int, int]],
) -> FindSnippet:
    """Build the snippet for the lines in ``window`` widened by ``context``."""
    first_line, last_line = window
    first = max(first_line - context, 0)
    last = min(last_line + context, len(lines) - 1)
    base = starts[first]
    content = "\n".join(lines[first : last + 1])
    highlights = [
        (max(start - base, 0), min(end - base, len(content)))
        for start, end in spans
        if end > base and start < base + len(content)
    ]
    return FindSnippet(line=first + 1, line_end=last + 1, text=content, highlights=highlights)


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

        relatives = self._matches(base, query.globs or [DEFAULT_GLOB])
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
        index, schema = self._build(relatives)
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
        generator: tantivy.SnippetGenerator | None = None
        if query.snippets:
            generator = tantivy.SnippetGenerator.create(searcher, parsed, schema, "body")
            generator.set_max_num_chars(query.snippet_chars)
        entries: list[FindEntry] = []
        for score, address in hits:
            relative = relatives[_doc_id(searcher, address)]
            snippets = (
                self._snippet(generator, searcher, address, query, text)
                if generator is not None
                else None
            )
            entries.append(self._entry(relative, score, snippets))
        return entries

    def _snippet(
        self,
        generator: tantivy.SnippetGenerator,
        searcher: tantivy.Searcher,
        address: tantivy.DocAddress,
        query: FindQuery,
        text: str,
    ) -> FindSnippet | None:
        """Locate the matched window in the stored text and turn it into line numbers.

        tantivy's highlighter only understands exact term and phrase queries, but fuzzy and
        prefix matching are on by default, so an empty fragment falls back to a token scan.
        """
        document = searcher.doc(address)
        snippet = generator.snippet_from_doc(document)
        fragment = snippet.fragment()
        body = cast("str", document["body"][0])
        lines = body.split("\n")
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line) + 1)
        if fragment.strip():
            located = self._located_fragment(body, fragment, snippet)
            if located is not None:
                offset, highlights = located
                first_line = body.count("\n", 0, offset)
                last_line = first_line + fragment.rstrip("\n").count("\n")
                spans = [(offset + start, offset + end) for start, end in highlights]
                return _snippet_model(lines, starts, (first_line, last_line), query.context, spans)
        return self._scanned_snippet(lines, starts, query, text)

    def _located_fragment(
        self, body: str, fragment: str, snippet: tantivy.Snippet
    ) -> tuple[int, list[tuple[int, int]]] | None:
        byte_ranges = [(item.start, item.end) for item in snippet.highlighted()]
        offset = body.find(fragment)
        if offset < 0:
            lead = fragment.index(fragment.lstrip())
            dropped = len(fragment[:lead].encode("utf-8"))
            fragment = fragment.lstrip()
            offset = body.find(fragment)
            if offset < 0:
                return None
            byte_ranges = [
                (max(start - dropped, 0), max(end - dropped, 0)) for start, end in byte_ranges
            ]
        highlights = [
            (_byte_to_char(fragment, start), _byte_to_char(fragment, end))
            for start, end in byte_ranges
        ]
        return offset, highlights

    def _scanned_snippet(
        self, lines: list[str], starts: list[int], query: FindQuery, text: str
    ) -> FindSnippet | None:
        if query.regex:
            return None
        terms = _query_terms(text)
        if not terms:
            return None
        best_index: int | None = None
        best_score = 0
        best_spans: list[tuple[int, int, int]] = []
        fuzzy = not query.exact
        for index, line in enumerate(lines):
            spans = _located_spans(line, terms, fuzzy=fuzzy)
            score = sum(quality for _, _, quality in spans)
            if score > best_score:
                best_score, best_index, best_spans = score, index, spans
        if best_index is None:
            return None
        base = starts[best_index]
        spans = [(base + start, base + end) for start, end, _ in best_spans]
        return _snippet_model(lines, starts, (best_index, best_index), query.context, spans)

    def _build(self, relatives: list[PurePosixPath]) -> tuple[tantivy.Index, tantivy.Schema]:
        builder = tantivy.SchemaBuilder()
        builder.add_text_field("path", stored=False)
        builder.add_text_field("body", stored=True)
        builder.add_integer_field("doc_id", stored=True)
        schema = builder.build()
        index = tantivy.Index(schema)
        writer = index.writer()
        for doc_id, relative in enumerate(relatives):
            writer.add_document(
                tantivy.Document(
                    path=relative.as_posix(), body=self._read_text(relative), doc_id=doc_id
                )
            )
        writer.commit()
        index.reload()
        return index, schema

    def _matches(self, base: PurePosixPath, patterns: list[str]) -> list[PurePosixPath]:
        directory = self.document_store.root / base
        if not directory.is_dir():
            return []
        matched = wcglob.glob(patterns, root_dir=str(directory.path), flags=wcglob.GLOBSTAR)
        relatives: list[PurePosixPath] = []
        for match in matched:
            relative = base / PurePosixPath(match)
            if (self.document_store.root / relative).is_file():
                relatives.append(relative)
        return relatives

    def _entry(
        self,
        relative: PurePosixPath,
        score: float | None,
        snippet: FindSnippet | None = None,
    ) -> FindEntry:
        membership = self.layout.resolve(relative)
        snippets = [snippet] if snippet is not None else []
        return FindEntry(
            path=relative,
            kind=membership.kind,
            plan=membership.plan,
            name=membership.name,
            score=score,
            snippets=snippets,
        )

    def _read_text(self, relative: PurePosixPath) -> str:
        try:
            return (self.document_store.root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
