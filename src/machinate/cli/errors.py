"""CLI error rendering: one place that maps a failure to a code and a short message.

Services raise domain errors; the storage layer raises path-scoped errors. This module is
the single boundary where either becomes a user-facing ``ErrorResult``, so no raw OS text
reaches the CLI.
"""

from dataclasses import dataclass

from pydantic import ValidationError

from machinate.models.operations import ErrorCode
from machinate.services.errors import (
    ServiceError,
    validation_failure_detail,
)
from machinate.storage.errors import StorageError

from .project_setup import ProjectError

#: A command failed at runtime; a structured error was already written.
EXIT_ERROR = 1
#: typer/click usage error (bad option or value).
EXIT_USAGE = 2


@dataclass
class ErrorDetail:
    code: ErrorCode
    message: str
    hint: str | None = None


def _describe_storage_error(exc: Exception) -> ErrorDetail | None:
    if isinstance(exc, StorageError):
        return ErrorDetail("storage", f"Could not access {exc.path}")
    return None


def describe_error(exc: Exception) -> ErrorDetail:
    """Render an exception as a machine code plus a concise, actionable message."""
    if isinstance(exc, ServiceError):
        return ErrorDetail(exc.code, str(exc), exc.hint)
    if isinstance(exc, ProjectError):
        return ErrorDetail("project", str(exc))
    if isinstance(exc, ValidationError):
        return ErrorDetail("input", validation_failure_detail(exc))
    detail = _describe_storage_error(exc)
    return detail if detail is not None else ErrorDetail("internal", "An internal error occurred")
