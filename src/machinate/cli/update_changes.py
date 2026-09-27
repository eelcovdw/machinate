"""Shared conversion of raw update options into validated update models."""

from dataclasses import dataclass

from pydantic import BaseModel

from .errors import InputError


@dataclass(frozen=True, slots=True)
class UpdateOptions:
    """Raw update options as parsed from the command line.

    ``status`` stays text; the target model validates it against that document's
    status literal. Tracking which options were supplied is the point: an omitted
    field must not reset a stored value.
    """

    summary: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    clear_tags: bool = False


def build_update[M: BaseModel](model: type[M], options: UpdateOptions, *, hint: str) -> M:
    """Build a validated update model from raw CLI options.

    Only the provided options become fields. ``hint`` names the options that would
    have an effect, for the error raised when nothing was passed.
    """
    changes: dict[str, object] = {}
    if options.summary is not None:
        changes["summary"] = options.summary
    if options.status is not None:
        changes["status"] = options.status
    if options.clear_tags:
        if options.tags is not None:
            msg = "--tag and --clear-tags are mutually exclusive."
            raise InputError(msg)
        changes["tags"] = []
    elif options.tags is not None:
        changes["tags"] = options.tags
    if not changes:
        msg = f"Nothing to update; pass {hint}."
        raise InputError(msg)
    return model.model_validate(changes)
