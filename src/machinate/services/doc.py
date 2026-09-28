from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.batch import BatchCreateError
from machinate.models.doc import Doc, DocUpdate
from machinate.services.batch import create_documents
from machinate.storage import (
    DocMetadata,
    Document,
    DocumentQuery,
    DocumentRecord,
    DocumentStore,
    Layout,
)
from machinate.storage.models import DocName, DocNameInput


class DocService:
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    @validate_call
    def create(self, name: DocName, metadata: DocMetadata, body: str = "") -> Doc:
        return self._create(name, metadata, body)

    def _create(self, name: DocName, metadata: DocMetadata, body: str = "") -> Doc:
        """Write a doc without re-checking anything; docs are project-level."""
        path = self.layout.doc(name)
        document = Document(metadata=metadata, body=body)
        self.document_store.create(path, document)
        return self._doc(path, name, document)

    @validate_call
    def create_batch(
        self, names: list[str], metadata: DocMetadata, body: str = ""
    ) -> tuple[list[Doc], list[BatchCreateError]]:
        """Create many docs, reporting per-name failures instead of aborting the batch."""
        return create_documents(
            names=names,
            document_store=self.document_store,
            validate_name=lambda name: DocNameInput(name=name).name,
            path_for=self.layout.doc,
            create=lambda name: self._create(name, metadata, body),
        )

    @validate_call
    def get(self, name: DocName) -> Doc:
        return self._get(name)

    def _read(self, name: DocName) -> tuple[PurePosixPath, Document[DocMetadata]]:
        path = self.layout.doc(name)
        return path, self.document_store.read(path, DocMetadata)

    def _doc(self, path: PurePosixPath, name: DocName, document: Document[DocMetadata]) -> Doc:
        """Build a doc from an already-loaded document, statting the file once."""
        return Doc(
            name=name,
            path=path,
            document=document,
            modified_at=self.document_store.metadata(path).modified,
        )

    def _get(self, name: DocName) -> Doc:
        path, document = self._read(name)
        return self._doc(path, name, document)

    @validate_call
    def info(self, name: DocName) -> DocumentRecord[DocMetadata]:
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
    def path(self, name: DocName) -> PurePosixPath:
        """Storage-relative doc path; validates the doc exists without parsing."""
        target = self.layout.doc(name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def update(self, name: DocName, changes: DocUpdate) -> Doc:
        path, document = self._read(name)
        if changes.apply_to(document):
            self.document_store.write(path, document)
        return self._doc(path, name, document)

    @validate_call
    def list(self, query: DocumentQuery | None = None) -> list[DocumentRecord[DocMetadata]]:
        return self.document_store.list(self.layout.docs_collection(), DocMetadata, query)
