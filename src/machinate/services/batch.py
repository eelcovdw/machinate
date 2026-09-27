"""Shared batch creation for task and context documents."""

from collections.abc import Callable
from pathlib import PurePosixPath

from pydantic import ValidationError

from machinate.models.batch import BatchCreateError, first_validation_message
from machinate.storage import DocumentStore
from machinate.storage.errors import MissingDocumentError, StorageError


def create_documents[DocumentT](
    *,
    names: list[str],
    document_store: DocumentStore,
    validate_name: Callable[[str], str],
    path_for: Callable[[str], PurePosixPath],
    create: Callable[[str], DocumentT],
) -> tuple[list[DocumentT], list[BatchCreateError]]:
    """Create one document per name, preflighting conflicts and reporting per-name failures.

    Invalid and already-existing names become BatchCreateError entries; every remaining name is
    still attempted, so a mid-batch failure cannot silently skip later names.
    """
    errors: list[BatchCreateError] = []
    candidates: list[str] = []
    for name in names:
        try:
            valid = validate_name(name)
        except ValidationError as exc:
            errors.append(BatchCreateError(name=name, error=first_validation_message(exc)))
            continue
        try:
            document_store.metadata(path_for(valid))
        except MissingDocumentError:
            candidates.append(valid)
        except StorageError as exc:
            errors.append(BatchCreateError(name=name, error=str(exc)))
        else:
            errors.append(BatchCreateError(name=name, error=f"Already exists: {path_for(valid)}"))
    created: list[DocumentT] = []
    for name in candidates:
        try:
            created.append(create(name))
        except (StorageError, ValidationError) as exc:
            errors.append(BatchCreateError(name=name, error=str(exc)))
    return created, errors
