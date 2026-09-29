from datetime import UTC, datetime
from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.documents import (
    NESTED_NAME_ADAPTER,
    DocMetadata,
    DocumentRecord,
    LoadedDocument,
    NestedName,
    ParsedDocument,
)
from machinate.models.operations import BatchCreated, CreateInput, DocumentQuery, DocumentUpdate
from machinate.services.batch import create_documents
from machinate.storage import DocumentStore, Layout


class DocService:
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    @staticmethod
    def _build_metadata(create: CreateInput) -> DocMetadata:
        return DocMetadata(created_at=datetime.now(UTC), summary=create.summary, tags=create.tags)

    def _record(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[DocMetadata]
    ) -> DocumentRecord[DocMetadata]:
        """Build a doc record, statting the file once."""
        return DocumentRecord[DocMetadata].from_document(
            document,
            name=name,
            path=path,
            modified_at=self.document_store.metadata(path).modified_at,
        )

    def _loaded(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[DocMetadata]
    ) -> LoadedDocument[DocMetadata]:
        return LoadedDocument(record=self._record(path, name, document), body=document.body)

    @validate_call
    def create(self, name: NestedName, create: CreateInput) -> LoadedDocument[DocMetadata]:
        return self._create(name, self._build_metadata(create))

    def _create(self, name: NestedName, metadata: DocMetadata) -> LoadedDocument[DocMetadata]:
        """Write a doc without re-checking anything; docs are project-level."""
        path = self.layout.doc(name)
        document = ParsedDocument(metadata=metadata, body="")
        self.document_store.create(path, document)
        return self._loaded(path, name, document)

    @validate_call
    def create_batch(
        self, names: list[str], create: CreateInput
    ) -> BatchCreated[LoadedDocument[DocMetadata]]:
        """Create many docs, reporting per-name failures instead of aborting the batch."""
        metadata = self._build_metadata(create)
        return create_documents(
            names=names,
            document_store=self.document_store,
            validate_name=NESTED_NAME_ADAPTER.validate_python,
            path_for=self.layout.doc,
            create=lambda name: self._create(name, metadata),
        )

    @validate_call
    def get(self, name: NestedName) -> LoadedDocument[DocMetadata]:
        return self._get(name)

    def _read(self, name: NestedName) -> tuple[PurePosixPath, ParsedDocument[DocMetadata]]:
        path = self.layout.doc(name)
        return path, self.document_store.read(path, DocMetadata)

    def _get(self, name: NestedName) -> LoadedDocument[DocMetadata]:
        path, document = self._read(name)
        return self._loaded(path, name, document)

    @validate_call
    def info(self, name: NestedName) -> DocumentRecord[DocMetadata]:
        path, document = self._read(name)
        return self._record(path, name, document)

    def directory(self) -> PurePosixPath:
        """Store-relative docs directory."""
        return self.layout.docs_collection().path

    @validate_call
    def path(self, name: NestedName) -> PurePosixPath:
        """Store-relative doc path; validates the doc exists without parsing."""
        target = self.layout.doc(name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def update(self, name: NestedName, changes: DocumentUpdate) -> LoadedDocument[DocMetadata]:
        path, document = self._read(name)
        updated = changes.apply_to(document)
        if updated is not None:
            self.document_store.write(path, updated)
            document = updated
        return self._loaded(path, name, document)

    @validate_call
    def list(self, query: DocumentQuery | None = None) -> list[DocumentRecord[DocMetadata]]:
        return self.document_store.list(self.layout.docs_collection(), DocMetadata, query)
