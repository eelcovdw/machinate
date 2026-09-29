"""Machine-readable error codes shared by the domain errors and the CLI result model."""

from typing import Literal

type ErrorCode = Literal[
    "input",
    "not_found",
    "exists",
    "invalid_document",
    "search_query",
    "storage",
    "project",
    "internal",
]
