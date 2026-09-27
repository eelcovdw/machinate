import io
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import override

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli import formatting
from machinate.cli.cli import app
from machinate.cli.models import ErrorResult
from machinate.cli.project_setup import prepare_project
from machinate.cli.styles import status_style
from machinate.storage import PlanMetadata, ProjectState, ProjectStateStore, TaskMetadata

runner = CliRunner()
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class _Tty(io.StringIO):
    @override
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_AGENT", "NO_COLOR"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    ProjectStateStore(UPath(root / ".machi/machinate.toml")).write(
        ProjectState(project_name="example")
    )
    application = prepare_project(root)
    application.plans.create(
        "auth",
        PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC), summary="Authentication"),
        body="# Auth\n\nDetails",
    )
    return root


def test_status_style_covers_known_states() -> None:
    assert status_style("active") == "green"
    assert status_style("done") == "blue"
    assert status_style("todo") == "yellow"
    assert status_style("in-progress") == "cyan"
    assert status_style("nonsense") == ""


def test_no_color_env_disables_styling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _Tty())
    assert "\x1b[" in formatting.render_text(ErrorResult(error="boom"))
    monkeypatch.setenv("NO_COLOR", "1")
    assert "\x1b[" not in formatting.render_text(ErrorResult(error="boom"))


def test_no_color_when_not_a_terminal(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["plan", "list"])
    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.stdout
    assert "auth" in result.stdout


def test_color_when_terminal(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(formatting, "_use_color", lambda: True)
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["plan", "show", "-p", "auth"], color=True)
    assert result.exit_code == 0, result.output
    assert "\x1b[" in result.stdout
    plain = ANSI.sub("", result.stdout)
    assert "Plan auth (draft)" in plain
    assert f"Path: {project / '.machi/plans/auth/plan.md'}" in plain
    assert "# Auth\n\nDetails" in plain


def test_status_badges_use_theme_colors(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(formatting, "_use_color", lambda: True)
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["plan", "list"], color=True)
    assert result.exit_code == 0, result.output
    assert "\x1b[2m" in result.stdout  # draft badge renders dim


def test_plan_list_groups_by_status(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    application.plans.create(
        "billing",
        PlanMetadata(created=datetime(2026, 1, 2, tzinfo=UTC), summary="Billing"),
        body="",
    )
    application.plans.set_status("billing", "active")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["plan", "list"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert "draft (1)" in out
    assert "active (1)" in out
    assert "done (0)" not in out  # only statuses present are shown
    assert out.index("draft (1)") < out.index("active (1)")
    assert "\u250c" not in out  # no table borders


def test_plan_list_no_group_by_keeps_sort_order(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = prepare_project(project)
    application.plans.create(
        "billing",
        PlanMetadata(created=datetime(2026, 1, 2, tzinfo=UTC), summary="Billing"),
        body="",
    )
    application.plans.set_status("auth", "active")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["plan", "list", "--no-group-by"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    # With grouping off, sort order wins: auth (active) before billing (draft).
    assert out.index("auth") < out.index("billing")
    assert "draft (1)" not in out
    assert "active" in out


def test_task_list_groups_by_status(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    for name in ("t1", "t2"):
        application.tasks.create(
            "auth", name, TaskMetadata(created=datetime(2026, 1, 1, tzinfo=UTC)), body=""
        )
    application.tasks.set_status("auth", "t2", "in-progress")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["task", "list", "-p", "auth"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert "todo (1)" in out
    assert "in-progress (1)" in out
    assert "done (0)" not in out


def test_task_list_no_group_by_keeps_sort_order(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = prepare_project(project)
    for name in ("t1", "t2"):
        application.tasks.create(
            "auth", name, TaskMetadata(created=datetime(2026, 1, 1, tzinfo=UTC)), body=""
        )
    application.tasks.set_status("auth", "t2", "in-progress")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["task", "list", "-p", "auth", "--no-group-by"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert "todo (1)" not in out
    assert out.index("t1") < out.index("t2")
    assert "todo" in out
    assert "in-progress" in out


def test_display_width_follows_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _Tty())
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setenv("LINES", "50")
    assert formatting._display_width() == 200


def test_display_width_defaults_when_not_a_terminal() -> None:
    assert formatting._display_width() == 120


def test_shorten_prefers_sentence_boundary() -> None:
    assert formatting._shorten("First sentence. Second sentence is much longer.", 20) == (
        "First sentence."
    )


def test_shorten_falls_back_to_word_boundary() -> None:
    assert formatting._shorten("one two three four five six", 15) == "one two three…"


def test_shorten_ignores_distant_sentence_boundary() -> None:
    assert formatting._shorten("Hi. This is a longer sentence here.", 20) == "Hi. This is a longer…"


def test_shorten_without_spaces_cuts_hard() -> None:
    assert formatting._shorten("abcdefghijklmnop", 8) == "abcdefgh…"


def test_shorten_leaves_short_text_untouched() -> None:
    assert formatting._shorten("already short", 50) == "already short"


def test_plan_list_truncates_long_summary(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    long_body = "This is a deliberately long summary sentence used to verify truncation. " * 3
    application = prepare_project(project)
    application.plans.create(
        "long", PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC)), body=long_body
    )
    monkeypatch.chdir(project)

    text = runner.invoke(app, ["plan", "list"])
    assert text.exit_code == 0, text.output
    assert "This is a deliberately long" in text.stdout
    assert long_body.strip() not in text.stdout

    payload = runner.invoke(app, ["plan", "list", "--format", "json"])
    assert payload.exit_code == 0, payload.output
    assert long_body.strip() in payload.stdout
