from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from machinate.storage.models import ContextMetadata, ContextName, Document, RelativePath
from machinate.storage.queries import DocumentRecord


class ContextUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    summary: str | None = None
    body: str = ""


class Context(BaseModel):
    name: ContextName
    path: RelativePath
    document: Document[ContextMetadata]
    modified_at: datetime


class ContextSummary(DocumentRecord[ContextMetadata]):
    pass
