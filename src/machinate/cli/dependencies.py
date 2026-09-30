import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import click

from .project_setup import ProjectServices, open_project
from .settings import Settings


@dataclass
class Dependencies:
    open_project: Callable[[Path | None], ProjectServices] = open_project
    settings: Settings | None = None

    def resolve_settings(self) -> Settings:
        """Return the injected settings, or load them from the environment."""
        return self.settings if self.settings is not None else Settings.from_environ(os.environ)


def get_dependencies(context: click.Context) -> Dependencies:
    dependencies = context.find_object(Dependencies)
    if dependencies is None:
        raise RuntimeError("CLI dependencies were not configured")
    return dependencies
