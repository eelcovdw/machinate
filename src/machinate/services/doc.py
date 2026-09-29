from datetime import UTC, datetime
from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.documents import (
    NESTED_NAME_ADAPTER,
    Doc,
    DocMetadata,
    DocumentRecord,
    NestedName,
    ParsedDocument,
)
from machinate.models.operations import BatchCreateError, CreateInput, DocumentQuery, DocUpdate
from machinate.services.batch import create_documents
from machinate.storage import DocumentStore, Layout


class DocService:
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    @staticmethod
    def _build_metadata(create: CreateInput) -> DocMetadata:
        return DocMetadata(created=datetime.now(UTC), summary=create.summary, tags=create.tags)

    @validate_call
    def create(self, name: NestedName, create: CreateInput, body: str = "") -> Doc:
        return self._create(name, self._build_metadata(create), body)

    def _create(self, name: NestedName, metadata: DocMetadata, body: str = "") -> Doc:
        """Write a doc without re-checking anything; docs are project-level."""
        path = self.layout.doc(name)
        document = ParsedDocument(metadata=metadata, body=body)
        self.document_store.create(path, document)
        return self._doc(path, name, document)

    @validate_call
    def create_batch(
        self, names: list[str], create: CreateInput, body: str = ""
    ) -> tuple[list[Doc], list[BatchCreateError]]:
        """Create many docs, reporting per-name failures instead of aborting the batch."""
        metadata = self._build_metadata(create)
        return create_documents(
            names=names,
            document_store=self.document_store,
            validate_name=NESTED_NAME_ADAPTER.validate_python,
            path_for=self.layout.doc,
            create=lambda name: self._create(name, metadata, body),
        )

    @validate_call
    def get(self, name: NestedName) -> Doc:
        return self._get(name)

    def _read(self, name: NestedName) -> tuple[PurePosixPath, ParsedDocument[DocMetadata]]:
        path = self.layout.doc(name)
        return path, self.document_store.read(path, DocMetadata)

    def _doc(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[DocMetadata]
    ) -> Doc:
        """Build a doc from an already-loaded document, statting the file once."""
        return Doc(
            name=name,
            path=path,
            document=document,
            modified_at=self.document_store.metadata(path).modified,
        )

    def _get(self, name: NestedName) -> Doc:
        path, document = self._read(name)
        return self._doc(path, name, document)

    @validate_call
    def info(self, name: NestedName) -> DocumentRecord[DocMetadata]:
        doc = self.get(name)
        return DocumentRecord[DocMetadata].from_document(
            doc.document,
            name=doc.name,
            path=doc.path,
            last_activity_at=doc.modified_at,
        )

    def directory(self) -> PurePosixPath:
        """Storage-relative docs directory."""
        return self.layout.docs_collection().path

    @validate_call
    def path(self, name: NestedName) -> PurePosixPath:
        """Storage-relative doc path; validates the doc exists without parsing."""
        target = self.layout.doc(name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def update(self, name: NestedName, changes: DocUpdate) -> Doc:
        path, document = self._read(name)
        if changes.apply_to(document):
            self.document_store.write(path, document)
        return self._doc(path, name, document)

    @validate_call
    def list(self, query: DocumentQuery | None = None) -> list[DocumentRecord[DocMetadata]]:
        return self.document_store.list(self.layout.docs_collection(), DocMetadata, query)
