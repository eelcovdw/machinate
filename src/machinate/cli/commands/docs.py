from pathlib import Path
from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import (
    DocAddResult,
    DocInfoResult,
    DocListResult,
    DocShowResult,
    DocUpdateResult,
    PathResult,
)
from machinate.cli.update_changes import UpdateOptions, build_update
from machinate.models.operations import BatchCreated, CreateInput, DocumentQuery, DocumentUpdate

_PROJECT = Annotated[
    Path | None,
    typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
]
_OUTPUT_FORMAT = Annotated[
    str | None, typer.Option("--format", help="Formatter name (text or json by default).")
]


def doc_changes(
    summary: str | None,
    tags: list[str] | None,
    clear_tags: bool = False,
) -> DocumentUpdate:
    """Validate provided options and build a doc update with only the changed fields."""
    return build_update(
        DocumentUpdate,
        UpdateOptions(summary=summary, tags=tags, clear_tags=clear_tags),
        hint="--summary, --tag, or --clear-tags",
    )


def doc_add(
    context: typer.Context,
    names: Annotated[list[str], typer.Argument(help="Name(s) of the document(s) to create.")],
    project: _PROJECT = None,
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tag", help="Tag(s) to apply to every created document. Repeat for multiple tags."
        ),
    ] = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Create one or more project-level documents."""
    with execute(context, "doc add", output_format) as run:
        project_context = run.prepare(project)
        batch = project_context.docs.create_batch(names, CreateInput(tags=tags or []))
        result = DocAddResult(
            command="doc add",
            project=project_context.project,
            batch=BatchCreated(created=[doc.record for doc in batch.created], errors=batch.errors),
        )
        run.render(result)
    if result.batch.errors:
        raise typer.Exit(1)  # Partial failure; the result still reports what was created.


def doc_list(  # noqa: PLR0913
    context: typer.Context,
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Match any tag. Repeat for multiple tags."),
    ] = None,
    sort: Annotated[str, typer.Option(help="Sort by name, created_at, or modified_at.")] = "name",
    descending: Annotated[bool, typer.Option(help="Reverse primary sort order.")] = False,
    limit: Annotated[str | None, typer.Option(help="Maximum results (positive integer).")] = None,
) -> None:
    """List project-level documents."""
    with execute(context, "doc list", output_format) as run:
        query = DocumentQuery.model_validate(
            {
                "tags": tags,
                "sort": sort,
                "descending": descending,
                "limit": limit,
            }
        )
        project_context = run.prepare(project)
        result = DocListResult(
            command="doc list",
            project=project_context.project,
            docs=project_context.docs.list(query),
        )
        run.render(result)


def doc_show(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the document to show.")],
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Show document metadata and body."""
    with execute(context, "doc show", output_format) as run:
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
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Show document metadata."""
    with execute(context, "doc info", output_format) as run:
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
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a document or the docs directory."""
    with execute(context, "doc path", output_format) as run:
        doc_name = name
        project_context = run.prepare(project)
        scope = project_context.project
        if doc_name is None:
            target = scope.storage / project_context.docs.directory()
            result = PathResult(
                command="doc path",
                project=scope,
                path=target,
                kind="docs_directory",
                exists=target.is_dir(),
            )
        else:
            target = scope.storage / project_context.docs.path(doc_name)
            result = PathResult(
                command="doc path",
                project=scope,
                path=target,
                kind="doc",
            )
        run.render(result)


def doc_update(  # noqa: PLR0913
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the document to update.")],
    project: _PROJECT = None,
    summary: Annotated[
        str | None,
        typer.Option("--summary", help="New summary; pass an empty string to clear it."),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Replace the document's tags. Repeat for multiple tags."),
    ] = None,
    clear_tags: Annotated[
        bool,
        typer.Option("--clear-tags", help="Remove all tags; mutually exclusive with --tag."),
    ] = False,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Change document summary or tags."""
    with execute(context, "doc update", output_format) as run:
        changes = doc_changes(summary, tags, clear_tags)
        project_context = run.prepare(project)
        updated = project_context.docs.update(name, changes)
        result = DocUpdateResult(
            command="doc update",
            project=project_context.project,
            doc=updated.record,
            body=updated.body,
        )
        run.render(result)
