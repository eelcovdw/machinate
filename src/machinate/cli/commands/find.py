from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from machinate.cli.dependencies import get_dependencies
from machinate.cli.errors import describe_error
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import ErrorResult, FindResult, ProjectScope
from machinate.cli.project_setup import ProjectError
from machinate.cli.settings import Settings
from machinate.models.search import DEFAULT_GLOB, FindQuery
from machinate.storage.errors import StorageError


def find_command(  # noqa: PLR0913
    context: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(help="Tantivy query; omit to list glob matches by path."),
    ] = None,
    glob: Annotated[
        list[str] | None,
        typer.Option("--glob", help="Filesystem glob relative to the base; repeat for OR."),
    ] = None,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Restrict the search to one plan."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    regex: Annotated[
        bool,
        typer.Option("--regex", help="Allow field-scoped regexes, e.g. path:/conf.*/."),
    ] = False,
    exact: Annotated[
        bool,
        typer.Option(
            "--exact", help="Disable fuzzy matching (one typo + prefix); exact terms only."
        ),
    ] = False,
    snippets: Annotated[
        bool,
        typer.Option(
            "--snippets/--no-snippets", help="Show matched lines and line ranges per result."
        ),
    ] = True,
    context_lines: Annotated[
        int,
        typer.Option("--context", help="Extra lines shown around each matched line."),
    ] = 0,
    snippet_chars: Annotated[
        int,
        typer.Option("--snippet-chars", help="Maximum characters per matched window."),
    ] = 160,
    limit: Annotated[
        str | None, typer.Option("--limit", help="Maximum results (positive integer).")
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    r"""Search files under the project's .machi store.

    QUERY uses the tantivy query language:

      term              token match; fuzzy (one typo) and prefix by default
      "two words"       phrase match
      "two words"~1     allowing one intervening word
      "two wo"*         phrase whose last word is a prefix
      field:term        restrict to a field (path or body)
      +term / -term     required / excluded
      a AND b, a OR b   boolean, AND binds tighter
      term^2            boost a term
      field:\[a TO c]    lexicographic range ({} for exclusive)
      field: IN \[a b]   set membership
      *                 every document

    Fuzzy matching tolerates one typo and matches prefixes; disable it with --exact.
    Regexes are field-scoped and need --regex, e.g. path:/conf.*/.

    Matches show the matched lines and their line range (path:12-14); use --no-snippets to
    list result paths only, or --context N to widen the shown window.
    """
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        format_name = output_format or settings.format
        formatter = select_formatter(format_name, dependencies.formatters)
        payload: dict[str, object] = {
            "query": query,
            "globs": glob or [],
            "regex": regex,
            "exact": exact,
            "snippets": snippets,
            "context": context_lines,
            "snippet_chars": snippet_chars,
        }
        if plan is not None:
            payload["plan"] = plan
        if limit is not None:
            payload["limit"] = limit
        find_query = FindQuery.model_validate(payload)
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        result = FindResult(
            project=scope,
            plan=find_query.plan,
            query=find_query.query,
            globs=find_query.globs or [DEFAULT_GLOB],
            entries=project_context.search.find(find_query),
        )
    except (
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        ValueError,
        OSError,
    ) as exc:
        typer.echo(
            formatter.format(ErrorResult(command="find", error=describe_error(exc), project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))
