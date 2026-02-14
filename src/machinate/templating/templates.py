from __future__ import annotations

from pydantic import BaseModel

from machinate.templating.frontmatter import (
    ContextFrontmatter,
    PlanFrontmatter,
    TaskFrontmatter,
    render_frontmatter,
)

DEFAULT_TEMPLATE = "# {entity}: {name}\n"


def render_template(
    frontmatter: BaseModel, name: str, *, entity: str, template: str = DEFAULT_TEMPLATE
) -> str:
    """Render frontmatter + markdown template."""
    body = template.format(entity=entity, name=name)
    return f"{render_frontmatter(frontmatter)}\n\n{body}"


def render_plan(name: str, *, template: str = DEFAULT_TEMPLATE) -> str:
    return render_template(PlanFrontmatter(), name, entity="Plan", template=template)


def render_task(name: str, *, template: str = DEFAULT_TEMPLATE) -> str:
    return render_template(TaskFrontmatter(), name, entity="Task", template=template)


def render_context(name: str, *, template: str = DEFAULT_TEMPLATE) -> str:
    return render_template(ContextFrontmatter(), name, entity="Context", template=template)
