"""CLI error rendering: one place that maps a failure to a code and a short message.

Services raise domain errors; the storage layer raises path-scoped errors. This module is
the single boundary where either becomes a user-facing ``ErrorResult``, so no raw OS text,
errno, absolute path, or pydantic dump reaches the CLI.
"""

from dataclasses import dataclass

from pydantic import ValidationError

from machinate.models.errors import ErrorCode
from machinate.services.errors import (
    InputError,
    PlanSelectionError,
    ServiceError,
    invalid_document_detail,
)
from machinate.storage.errors import (
    DocumentExistsError,
    MissingDocumentError,
    StorageError,
)
from machinate.storage.errors import (
    InvalidDocumentError as StorageInvalidDocumentError,
)

from .formatting import UnknownFormatError
from .project_setup import ProjectError

__all__ = [
    "EXIT_ERROR",
    "EXIT_USAGE",
    "ErrorDetail",
    "InputError",
    "PlanSelectionError",
    "describe_error",
]

#: A command failed at runtime; a structured error was already written.
EXIT_ERROR = 1
#: typer/click usage error (bad option or value).
EXIT_USAGE = 2


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: ErrorCode
    message: str


def _validation_message(exc: ValidationError) -> str:
    error = exc.errors()[0]
    field = ".".join(str(part) for part in error["loc"] if part != "self")
    message = str(error["msg"]).removeprefix("Value error, ")
    return f"{field}: {message}" if field else message


def _describe_storage_error(exc: Exception) -> ErrorDetail | None:
    if isinstance(exc, MissingDocumentError):
        return ErrorDetail("not_found", f"{exc.path} not found")
    if isinstance(exc, DocumentExistsError):
        return ErrorDetail("exists", f"{exc.path} already exists")
    if isinstance(exc, StorageInvalidDocumentError):
        detail = invalid_document_detail(exc.reason)
        return ErrorDetail("invalid_document", f"{exc.path}: {detail}")
    if isinstance(exc, StorageError):
        return ErrorDetail("storage", f"Could not access {exc.path}")
    return None


def describe_error(exc: Exception) -> ErrorDetail:
    """Render an exception as a machine code plus a concise, actionable message."""
    if isinstance(exc, ServiceError):
        return ErrorDetail(exc.code, str(exc))
    if isinstance(exc, ProjectError):
        return ErrorDetail("project", str(exc))
    if isinstance(exc, UnknownFormatError):
        return ErrorDetail("input", str(exc))
    if isinstance(exc, ValidationError):
        return ErrorDetail("input", _validation_message(exc))
    detail = _describe_storage_error(exc)
    return detail if detail is not None else ErrorDetail("internal", str(exc))
