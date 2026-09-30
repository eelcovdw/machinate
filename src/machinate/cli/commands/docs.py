from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import (
    DocAddResult,
    DocInfoResult,
    DocListResult,
    DocShowResult,
    DocUpdateResult,
)
from machinate.cli.options import (
    CLEAR_TAGS,
    DESCENDING,
    LIMIT,
    MATCH_TAGS,
    OUTPUT_FORMAT,
    PROJECT_DIR,
    SORT,
    SUMMARY,
    TAGS,
)
from machinate.cli.update_options import UpdateOptions, build_update
from machinate.models.operations import BatchCreated, CreateInput, DocumentQuery, DocumentUpdate


def doc_add_command(  # noqa: PLR0913
    ctx: typer.Context,
    names: Annotated[list[str], typer.Argument(help="Name(s) of the docs to create.")],
    project_directory: PROJECT_DIR = None,
    tags: TAGS = None,
    summary: SUMMARY = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Create one or more project-level docs."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        batch = services.docs.create_many(names, CreateInput(tags=tags or [], summary=summary))
        result = DocAddResult(
            command="doc add",
            project=services.project,
            batch=BatchCreated(
                created=[doc.record for doc in batch.created], failures=batch.failures
            ),
        )
        run.render(result)


def doc_list_command(  # noqa: PLR0913
    ctx: typer.Context,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
    tags: MATCH_TAGS = None,
    sort: SORT = "name",
    descending: DESCENDING = False,
    limit: LIMIT = None,
) -> None:
    """List project-level docs."""
    with execute(ctx, output_format) as run:
        query = DocumentQuery(
            tags=set(tags) if tags is not None else None,
            sort=sort,
            descending=descending,
            limit=limit,
        )
        services = run.open_project(project_directory)
        result = DocListResult(
            command="doc list",
            project=services.project,
            docs=services.docs.list_records(query),
        )
        run.render(result)


def doc_show_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the doc to show.")],
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show doc metadata and body."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        document = services.docs.get(name)
        result = DocShowResult(
            command="doc show",
            project=services.project,
            doc=document.record,
            body=document.body,
        )
        run.render(result)


def doc_info_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the doc to inspect.")],
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show doc metadata."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        document = services.docs.get_info(name)
        result = DocInfoResult(command="doc info", project=services.project, doc=document)
        run.render(result)


def doc_path_command(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Doc name; omit to print the docs directory."),
    ] = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a doc or the docs directory."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        located = services.docs.locate(name)
        run.render_path(command="doc path", plan_name=None, located=located)


def doc_update_command(  # noqa: PLR0913
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the doc to update.")],
    project_directory: PROJECT_DIR = None,
    summary: SUMMARY = None,
    tags: TAGS = None,
    clear_tags: CLEAR_TAGS = False,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Change doc summary or tags."""
    with execute(ctx, output_format) as run:
        update = build_update(
            DocumentUpdate,
            UpdateOptions(summary=summary, tags=tags, clear_tags=clear_tags),
            hint="--summary, --tag, or --clear-tags",
        )
        services = run.open_project(project_directory)
        updated = services.docs.update(name, update)
        result = DocUpdateResult(
            command="doc update",
            project=services.project,
            doc=updated.record,
            body=updated.body,
        )
        run.render(result)
