from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import FindResult
from machinate.cli.options import LIMIT, OUTPUT_FORMAT, PLAN, PROJECT
from machinate.models.operations import FindQuery


def find_command(  # noqa: PLR0913
    context: typer.Context,
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
    project: PROJECT = None,
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
    r"""Search files under the project's .machi store.

    Scope

      By default every plan in the project is searched. --plan narrows the
      search to one plan; --project targets an exact project directory
      instead of discovering one upward.

    QUERY allows one typo and prefix matching by default: `authent`
    matches `authentication`. `--exact` disables both. Quote phrases: an
    unquoted multi-word query is rejected as extra arguments.

    --glob filters by filesystem path and is ANDed with QUERY; repeats are
    ORed. Patterns are relative to the search scope -- the .machi store
    without --plan, the selected plan's directory with --plan -- so quote
    them and include the `plans/` prefix only at project scope. Regexes
    are field-scoped and need --regex.

    Examples

      machi find auth
      machi find '"auth token"'
      machi find body:config --plan v2
      machi find --glob 'plans/*/tasks/**/*.md'
      machi find --plan v2 --glob 'tasks/**/*.md'
      machi find 'path:/conf.*/' --regex

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

    Results list matching paths only.
    """
    with execute(context, "find", output_format) as run:
        find_query = FindQuery(
            query=query,
            globs=glob or [],
            plan=plan,
            limit=limit,
            regex=regex,
            exact=exact,
        )
        project_context = run.prepare(project)
        matches = project_context.search.find(find_query)
        run.render(
            FindResult(
                command="find",
                project=project_context.project,
                plan=find_query.plan,
                query=find_query.query,
                globs=matches.globs,
                entries=matches.entries,
                skipped=matches.skipped,
            )
        )
