"""Shared batch creation for the plan, task, context, and doc resources."""

from collections.abc import Callable
from pathlib import PurePosixPath

from pydantic import ValidationError

from machinate.models.operations import BatchCreated, CreateFailure
from machinate.services.errors import ExistsError, ServiceError, validation_failure_detail
from machinate.storage import DocumentStore
from machinate.storage.errors import MissingDocumentError, StorageError


def create_many[DocumentT](
    *,
    names: list[str],
    document_store: DocumentStore,
    validate_name: Callable[[str], str],
    path_for: Callable[[str], PurePosixPath],
    create: Callable[[str], DocumentT],
) -> BatchCreated[DocumentT]:
    """Create one document per name, preflighting conflicts and reporting per-name failures.

    Names are deduplicated during preflight; failures keep input order and carry a machine
    reason next to the message. Every remaining name is still attempted, so a mid-batch
    failure cannot silently skip later names.
    """
    preflight = _preflight_names(names, document_store, validate_name, path_for)
    return _create_pending(preflight, names, create)


def _preflight_names(
    names: list[str],
    document_store: DocumentStore,
    validate_name: Callable[[str], str],
    path_for: Callable[[str], PurePosixPath],
) -> list[CreateFailure | None]:
    """Validate and dedupe names; an entry is the rejection, or None when free to create."""
    slots: list[CreateFailure | None] = [None] * len(names)
    seen: set[str] = set()
    for index, name in enumerate(names):
        try:
            valid = validate_name(name)
        except ValidationError as exc:
            slots[index] = CreateFailure(
                name=name, reason="invalid_name", message=validation_failure_detail(exc)
            )
            continue
        if valid.casefold() in seen:
            slots[index] = CreateFailure(
                name=name, reason="exists", message="Duplicate name in this batch"
            )
            continue
        seen.add(valid.casefold())
        slots[index] = _existing_error(document_store, path_for(valid), name)
    return slots


def _existing_error(
    document_store: DocumentStore, target: PurePosixPath, name: str
) -> CreateFailure | None:
    """None when the target is free; otherwise the reason it cannot be created."""
    try:
        document_store.stat(target)
    except MissingDocumentError:
        return None
    except StorageError as exc:
        return CreateFailure(name=name, reason="failed", message=str(exc))
    return CreateFailure(name=name, reason="exists", message="Already exists")


def _create_pending[DocumentT](
    slots: list[CreateFailure | None],
    names: list[str],
    create: Callable[[str], DocumentT],
) -> BatchCreated[DocumentT]:
    """Create each free slot in input order, recording per-name failures in input order."""
    created: list[DocumentT] = []
    failures: list[CreateFailure] = []
    for index, slot in enumerate(slots):
        if slot is not None:
            failures.append(slot)
            continue
        try:
            created.append(create(names[index]))
        except ExistsError as exc:
            failures.append(CreateFailure(name=names[index], reason="exists", message=str(exc)))
        except ServiceError as exc:
            failures.append(CreateFailure(name=names[index], reason="failed", message=str(exc)))
        except StorageError as exc:
            failures.append(CreateFailure(name=names[index], reason="failed", message=str(exc)))
        except ValidationError as exc:
            failures.append(
                CreateFailure(
                    name=names[index],
                    reason="failed",
                    message=validation_failure_detail(exc),
                )
            )
    return BatchCreated(created=created, failures=failures)
