from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import SearchResult
from machinate.cli.options import LIMIT, OUTPUT_FORMAT, PLAN, PROJECT_DIR
from machinate.models.operations import SearchQuery


def search_command(  # noqa: PLR0913
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(help="Tantivy query; omit to list glob matches by path."),
    ] = None,
    glob: Annotated[
        list[str] | None,
        typer.Option(
            "--glob", help="Filesystem glob relative to the base (quote it); repeat for OR."
        ),
    ] = None,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
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
    limit: LIMIT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Search files under the project's .machi store.

    \b
    Scope

    \b
      By default every plan and all docs are searched. --plan narrows the
      search to one plan; --project-dir targets an exact project directory
      instead of discovering one upward.

    \b
    QUERY allows one typo and prefix matching by default: `authent`
    matches `authentication`. `--exact` disables both. Quote phrases: an
    unquoted multi-word query is rejected as extra arguments.

    \b
    --glob filters by filesystem path and is ANDed with QUERY; repeats are
    ORed. Patterns are relative to the search scope -- the .machi store
    without --plan, the selected plan's directory with --plan -- so quote
    them and include the `plans/` prefix only at project scope. Regexes
    are field-scoped and need --regex.

    \b
    Examples

    \b
      machi search auth
      machi search '"auth token"'
      machi search body:config --plan v2
      machi search --glob 'plans/*/tasks/**/*.md'
      machi search --plan v2 --glob 'tasks/**/*.md'
      machi search 'path:/conf.*/' --regex

    \b
    QUERY uses the tantivy query language:

    \b
      term              token match; fuzzy (one typo) and prefix by default
      "two words"       phrase match
      "two words"~1     allowing one intervening word
      "two wo"*         phrase whose last word is a prefix
      field:term        restrict to a field (path or body)
      +term / -term     required / excluded
      a AND b, a OR b   boolean, AND binds tighter
      term^2            boost a term
      field:\\[a TO c]    lexicographic range ({} for exclusive)
      field: IN \\[a b]   set membership
      *                 every document

    \b
    Results list matching paths only.
    """
    with execute(ctx, output_format) as run:
        search_query = SearchQuery(
            query=query,
            globs=glob or [],
            plan=plan,
            limit=limit,
            allow_regex=regex,
            is_exact=exact,
        )
        services = run.open_project(project_directory)
        matches = services.search.search(search_query)
        run.render(
            SearchResult(
                command="search",
                project=services.project,
                plan_name=search_query.plan,
                query=search_query.query,
                globs=matches.globs,
                matches=matches.matches,
                skipped=matches.skipped,
            )
        )
