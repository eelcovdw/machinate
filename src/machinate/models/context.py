from datetime import datetime

from pydantic import BaseModel

from machinate.models.update import DocumentUpdate
from machinate.storage.models import ContextMetadata, ContextName, Document, RelativePath


class ContextUpdate(DocumentUpdate):
    """A context update adds no fields beyond the shared ones."""


class Context(BaseModel):
    name: ContextName
    path: RelativePath
    document: Document[ContextMetadata]
    modified_at: datetime
