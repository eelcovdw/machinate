from pathlib import PurePosixPath

import pytest
from pydantic import ValidationError

from machinate.cli.errors import EXIT_ERROR, EXIT_USAGE, describe_error
from machinate.cli.project_setup import ProjectError
from machinate.models.documents import PlanMetadata
from machinate.models.operations import ErrorCode
from machinate.services.errors import (
    ExistsError,
    InputError,
    InvalidDocumentError,
    NotFoundError,
    SearchQueryError,
)
from machinate.storage.errors import MissingDocumentError


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (InputError("bad value"), "input"),
        (NotFoundError("plan", "auth"), "not_found"),
        (ExistsError("plan", "auth"), "exists"),
        (InvalidDocumentError("plans/auth/plan.md", "bad frontmatter"), "invalid_document"),
        (SearchQueryError("unbalanced quote"), "search_query"),
        (MissingDocumentError(PurePosixPath("plans/auth/plan.md")), "storage"),
        (ProjectError("no project"), "project"),
        (RuntimeError("raw internal text"), "internal"),
    ],
)
def test_describe_error_maps_each_code(exception: Exception, code: ErrorCode) -> None:
    detail = describe_error(exception)
    assert detail.code == code
    assert detail.message


def test_describe_error_drops_os_text() -> None:
    detail = describe_error(MissingDocumentError(PurePosixPath("plans/auth/plan.md")))
    assert "[Errno" not in detail.message
    assert "raw internal text" not in describe_error(RuntimeError("raw internal text")).message


def test_validation_error_is_input() -> None:
    with pytest.raises(ValidationError) as error:
        PlanMetadata.model_validate({"created_at": "not-a-date"})
    detail = describe_error(error.value)
    assert detail.code == "input"
    assert "created_at" in detail.message


def test_exit_codes() -> None:
    assert EXIT_ERROR == 1
    assert EXIT_USAGE == 2
