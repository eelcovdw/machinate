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
    PROJECT,
    SORT,
    SUMMARY,
    TAGS,
)
from machinate.cli.update_changes import UpdateOptions, build_update
from machinate.models.operations import BatchCreated, CreateInput, DocumentQuery, DocumentUpdate


def doc_add(  # noqa: PLR0913
    context: typer.Context,
    names: Annotated[list[str], typer.Argument(help="Name(s) of the document(s) to create.")],
    project: PROJECT = None,
    tags: TAGS = None,
    summary: SUMMARY = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Create one or more project-level documents."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project)
        batch = project_context.docs.create_batch(
            names, CreateInput(tags=tags or [], summary=summary)
        )
        result = DocAddResult(
            command="doc add",
            project=project_context.project,
            batch=BatchCreated(created=[doc.record for doc in batch.created], errors=batch.errors),
        )
        run.render(result)


def doc_list(  # noqa: PLR0913
    context: typer.Context,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
    tags: MATCH_TAGS = None,
    sort: SORT = "name",
    descending: DESCENDING = False,
    limit: LIMIT = None,
) -> None:
    """List project-level documents."""
    with execute(context, output_format) as run:
        query = DocumentQuery(
            tags=set(tags) if tags is not None else None,
            sort=sort,
            descending=descending,
            limit=limit,
        )
        project_context = run.prepare(project)
        result = DocListResult(
            command="doc list",
            project=project_context.project,
            docs=project_context.docs.list_records(query),
        )
        run.render(result)


def doc_show(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the document to show.")],
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show document metadata and body."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project)
        document = project_context.docs.get(name)
        result = DocShowResult(
            command="doc show",
            project=project_context.project,
            doc=document.record,
            body=document.body,
        )
        run.render(result)


def doc_info(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the document to inspect.")],
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show document metadata."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project)
        document = project_context.docs.info(name)
        result = DocInfoResult(command="doc info", project=project_context.project, doc=document)
        run.render(result)


def doc_path(
    context: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Document name; omit to print the docs directory."),
    ] = None,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a document or the docs directory."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project)
        located = project_context.docs.locate(name)
        run.render_path(command="doc path", plan=None, located=located)


def doc_update(  # noqa: PLR0913
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the document to update.")],
    project: PROJECT = None,
    summary: SUMMARY = None,
    tags: TAGS = None,
    clear_tags: CLEAR_TAGS = False,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Change document summary or tags."""
    with execute(context, output_format) as run:
        changes = build_update(
            DocumentUpdate,
            UpdateOptions(summary=summary, tags=tags, clear_tags=clear_tags),
            hint="--summary, --tag, or --clear-tags",
        )
        project_context = run.prepare(project)
        updated = project_context.docs.update(name, changes)
        result = DocUpdateResult(
            command="doc update",
            project=project_context.project,
            doc=updated.record,
            body=updated.body,
        )
        run.render(result)
