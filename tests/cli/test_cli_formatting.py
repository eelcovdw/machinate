import io
import re
import sys
from pathlib import Path
from typing import override

import pytest
from harness import DEFAULT_DEPENDENCIES, seed_plan
from typer.testing import CliRunner

from machinate.cli import formatting
from machinate.cli.cli import build_cli
from machinate.cli.models import ErrorResult
from machinate.cli.project_setup import open_project
from machinate.models.documents import PlanStatus
from machinate.models.operations import StatusUpdate

runner = CliRunner()
app = build_cli(DEFAULT_DEPENDENCIES)
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class _Tty(io.StringIO):
    @override
    def isatty(self) -> bool:
        return True


@pytest.fixture
def auth_project(project: Path) -> Path:
    seed_plan(project, "auth", summary="Authentication", body="# Auth\n\nDetails")
    return project


def test_no_color_env_disables_styling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _Tty())
    assert "\x1b[" in formatting.render_text(
        ErrorResult(command="plan list", error="boom", code="input")
    )
    monkeypatch.setenv("NO_COLOR", "1")
    assert "\x1b[" not in formatting.render_text(
        ErrorResult(command="plan list", error="boom", code="input")
    )


def test_no_color_when_not_a_terminal(auth_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(auth_project)
    result = runner.invoke(app, ["plan", "list"])
    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.stdout
    assert "auth" in result.stdout


def test_plan_list_groups_by_status(auth_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(auth_project, "billing", status="active", summary="Billing")
    monkeypatch.chdir(auth_project)
    result = runner.invoke(app, ["plan", "list"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert "draft (1)" in out
    assert "active (1)" in out
    assert "done (0)" not in out  # only statuses present are shown
    assert out.index("draft (1)") < out.index("active (1)")


def test_plan_list_no_group_by_keeps_sort_order(
    auth_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_plan(auth_project, "billing", summary="Billing")
    application = open_project(auth_project)
    application.plans.update("auth", StatusUpdate[PlanStatus](status="active"))
    monkeypatch.chdir(auth_project)
    result = runner.invoke(app, ["plan", "list", "--no-group"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    # With grouping off, sort order wins: auth before billing.
    assert out.index("auth") < out.index("billing")
    assert "draft (1)" not in out
    assert "active" in out


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("First sentence. Second sentence is much longer.", 20, "First sentence."),
        ("one two three four five six", 15, "one two three…"),
        ("Hi. This is a longer sentence here.", 20, "Hi. This is a longer…"),
        ("abcdefghijklmnop", 8, "abcdefgh…"),
        ("already short", 50, "already short"),
    ],
)
def test_shorten(text: str, limit: int, expected: str) -> None:
    assert formatting._shorten(text, limit) == expected


def test_plan_list_truncates_long_summary(
    auth_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    long_body = "This is a deliberately long summary sentence used to verify truncation. " * 3
    seed_plan(auth_project, "long", body=long_body)
    monkeypatch.chdir(auth_project)

    text = runner.invoke(app, ["plan", "list"])
    assert text.exit_code == 0, text.output
    assert "This is a deliberately long" in text.stdout
    assert long_body.strip() not in text.stdout

    payload = runner.invoke(app, ["plan", "list", "--format", "json"])
    assert payload.exit_code == 0, payload.output
    assert long_body.strip() in payload.stdout
