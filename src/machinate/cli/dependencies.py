import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import click
from pydantic import ValidationError

from .formatting import Formatter, TextFormatter
from .models import ProjectScope
from .project_setup import ProjectContext, initialize_project, prepare_project
from .settings import Settings


def default_formatters() -> dict[str, Formatter]:
    return {"json": Formatter(), "text": TextFormatter()}


@dataclass(frozen=True)
class Dependencies:
    formatters: Mapping[str, Formatter] = field(default_factory=default_formatters)
    prepare_project: Callable[[Path | None], ProjectContext] = prepare_project
    initialize_project: Callable[[Path | None, str | None], ProjectScope] = initialize_project
    settings: Settings | None = None

    def resolve_settings(self) -> Settings:
        """Return the injected settings, or load them from the environment."""
        return self.settings if self.settings is not None else Settings.from_environ(os.environ)


def get_dependencies(context: click.Context) -> Dependencies:
    dependencies = context.find_object(Dependencies)
    if dependencies is None:
        raise RuntimeError("CLI dependencies were not configured")
    return dependencies


_SETTINGS_KEY = "machinate_settings"


def get_settings(context: click.Context) -> Settings:
    """Return this invocation's settings, loading them from the environment only once."""
    cached = cast("Settings | Exception | None", context.meta.get(_SETTINGS_KEY))
    if isinstance(cached, Exception):
        raise cached
    if cached is not None:
        return cached
    try:
        settings = get_dependencies(context).resolve_settings()
    except ValidationError as exc:
        context.meta[_SETTINGS_KEY] = exc
        raise
    context.meta[_SETTINGS_KEY] = settings
    return settings
