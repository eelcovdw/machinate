from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from machinate.storage.models import Document, Metadata, Tag


class DocumentUpdate(BaseModel):
    """Fields a document update may change; subclasses add domain-specific ones."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    body: str = ""
    summary: str | None = None
    tags: list[Tag] | None = None

    def apply_to[M: Metadata](self, document: Document[M]) -> bool:
        """Apply this update's shared fields to a loaded document; report whether it changed.

        Subclass-specific fields (such as a status) are the caller's responsibility.
        """
        if not self.model_fields_set:
            return False
        if "body" in self.model_fields_set:
            document.body = self.body
        if "summary" in self.model_fields_set:
            document.metadata.summary = self.summary or None
        if "tags" in self.model_fields_set:
            document.metadata.tags = self.tags if self.tags is not None else []
        return True
