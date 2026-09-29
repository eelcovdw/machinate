"""Domain errors raised by services.

Services translate storage and validation failures into these; the CLI maps each one to a
short message and a machine-readable code in a single place.
"""

from typing import ClassVar

from pydantic import ValidationError

from machinate.models.errors import ErrorCode


class ServiceError(Exception):
    """Base class for a failure a service reports to its caller."""

    code: ClassVar[ErrorCode] = "internal"


class InputError(ServiceError):
    """CLI options are missing, contradictory, or otherwise unusable."""

    code: ClassVar[ErrorCode] = "input"


class PlanSelectionError(InputError):
    """A command needs a plan but none was given, selected, or still exists."""

    code: ClassVar[ErrorCode] = "input"


class NotFoundError(ServiceError):
    """A document the caller referenced does not exist."""

    code: ClassVar[ErrorCode] = "not_found"

    def __init__(self, kind: str, name: str) -> None:
        self.kind: str = kind
        self.name: str = name
        super().__init__(f"{kind} {name!r} not found")


class ExistsError(ServiceError):
    """A document the caller is creating already exists."""

    code: ClassVar[ErrorCode] = "exists"

    def __init__(self, kind: str, name: str) -> None:
        self.kind: str = kind
        self.name: str = name
        super().__init__(f"{kind} {name!r} already exists")


class InvalidDocumentError(ServiceError):
    """A stored document cannot be parsed or its frontmatter is invalid."""

    code: ClassVar[ErrorCode] = "invalid_document"

    def __init__(self, path: str, detail: str) -> None:
        self.path: str = path
        self.detail: str = detail
        super().__init__(f"{path}: {detail}")


class SearchQueryError(ServiceError):
    """The search query string could not be parsed."""

    code: ClassVar[ErrorCode] = "search_query"


def invalid_document_detail(reason: Exception | None) -> str:
    """Render a parse failure as `field: message`, without pydantic's dump or URL."""
    if isinstance(reason, ValidationError):
        error = reason.errors()[0]
        field = ".".join(str(part) for part in error["loc"])
        message = str(error["msg"]).removeprefix("Value error, ")
        return f"{field}: {message}" if field else message
    return str(reason) if reason is not None else "invalid document"
