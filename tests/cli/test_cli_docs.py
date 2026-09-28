import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import PathResult
from machinate.cli.project_setup import prepare_project
from machinate.storage import DocMetadata, ProjectState, ProjectStateStore

runner = CliRunner()
_CREATED = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    ProjectStateStore(root / ".machi/machinate.toml").write(ProjectState(project_name="example"))
    return root


def test_doc_group_runs_without_a_plan(project: Path) -> None:
    """Every doc subcommand works with no plan selected and no -p."""
    invocations = [
        ["doc", "add", "spec"],
        ["doc", "list"],
        ["doc", "show", "spec"],
        ["doc", "info", "spec"],
        ["doc", "path", "spec"],
        ["doc", "update", "spec", "--summary", "x"],
    ]
    for args in invocations:
        result = runner.invoke(app, [*args, "-P", str(project), "--format", "json"])
        assert result.exit_code == 0, (args, result.output)


def test_doc_path_reports_project_paths(project: Path) -> None:
    prepare_project(project).docs.create("spec", DocMetadata(created=_CREATED))

    directory = runner.invoke(app, ["doc", "path", "-P", str(project), "--format", "json"])
    assert directory.exit_code == 0, directory.output
    folder = PathResult.model_validate(json.loads(directory.stdout))
    assert folder.kind == "docs_directory"
    assert folder.plan is None
    assert folder.path == project / ".machi/docs"

    file = runner.invoke(app, ["doc", "path", "spec", "-P", str(project), "--format", "json"])
    assert file.exit_code == 0, file.output
    target = PathResult.model_validate(json.loads(file.stdout))
    assert target.kind == "doc"
    assert target.plan is None
    assert target.path == project / ".machi/docs/spec.md"


def test_doc_add_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed = application.docs.create("seed", DocMetadata(created=_CREATED))
    create_batch = Mock(return_value=([seed], []))
    monkeypatch.setattr(application.docs, "create_batch", create_batch)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["doc", "add", "spec", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    create_batch.assert_called_once()
