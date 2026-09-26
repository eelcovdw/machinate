from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import click

from .formatting import Formatter, TextFormatter
from .project_setup import ProjectContext, prepare_project


def default_formatters() -> dict[str, Formatter]:
    return {"json": Formatter(), "text": TextFormatter()}


@dataclass(frozen=True)
class Dependencies:
    formatters: Mapping[str, Formatter] = field(default_factory=default_formatters)
    prepare_project: Callable[[Path | None], ProjectContext] = prepare_project


def get_dependencies(context: click.Context) -> Dependencies:
    dependencies = context.find_object(Dependencies)
    if dependencies is None:
        raise RuntimeError("CLI dependencies were not configured")
    return dependencies
