from datetime import datetime

from pydantic import BaseModel

from machinate.models.update import DocumentUpdate
from machinate.storage.models import DocMetadata, DocName, Document, RelativePath


class DocUpdate(DocumentUpdate):
    """A doc update adds no fields beyond the shared ones."""


class Doc(BaseModel):
    name: DocName
    path: RelativePath
    document: Document[DocMetadata]
    modified_at: datetime
