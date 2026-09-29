from pathlib import Path

from harness import cli, seed

from machinate.cli.models import InfoResult, PlanInfoResult
from machinate.models.operations import PlanOverview, ProjectOverview
from machinate.storage import ProjectState, ProjectStateStore


def test_info_project_overview(project: Path) -> None:
    seed.plan(project, "auth")
    seed.plan(project, "billing", status="active")
    seed.task(project, "auth", "design", status="done")
    seed.task(project, "auth", "implement")
    seed.context(project, "auth", "spec")

    parsed = cli.json(InfoResult, ["info", "-P", str(project), "--format", "json"])
    assert parsed.command == "info"
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert isinstance(parsed.overview, ProjectOverview)
    overview = parsed.overview
    assert overview.current_plan is None
    assert overview.selection_valid is True
    assert overview.plan_count == 2
    assert overview.plans_by_status == {"draft": 1, "active": 1, "done": 0}
    assert overview.task_totals == {"todo": 1, "in-progress": 0, "done": 1}
    assert overview.context_count == 1
    assert {plan.name for plan in overview.recent_plans} == {"auth", "billing"}


def test_info_project_overview_current_plan(project: Path) -> None:
    seed.plan(project, "auth")
    ProjectStateStore(project / ".machi/machinate.toml").write(
        ProjectState(project_name="example", current_plan="auth")
    )

    overview = cli.json(InfoResult, ["info", "-P", str(project), "--format", "json"]).overview
    assert isinstance(overview, ProjectOverview)
    assert overview.current_plan == "auth"
    assert overview.selection_valid is True


def test_info_project_overview_stale_selection(project: Path) -> None:
    ProjectStateStore(project / ".machi/machinate.toml").write(
        ProjectState(project_name="example", current_plan="ghost")
    )
    overview = cli.json(InfoResult, ["info", "-P", str(project), "--format", "json"]).overview
    assert isinstance(overview, ProjectOverview)
    assert overview.current_plan == "ghost"
    assert overview.selection_valid is False


def test_info_project_overview_limits_recent_plans(tmp_path: Path) -> None:
    root = tmp_path / "project"
    ProjectStateStore(root / ".machi/machinate.toml").write(ProjectState(project_name="example"))
    for index in range(6):
        seed.plan(root, f"plan{index}")
    overview = cli.json(InfoResult, ["info", "-P", str(root), "--format", "json"]).overview
    assert isinstance(overview, ProjectOverview)
    assert overview.plan_count == 6
    assert len(overview.recent_plans) == 5


def test_info_empty_project(project: Path) -> None:
    overview = cli.json(InfoResult, ["info", "-P", str(project), "--format", "json"]).overview
    assert isinstance(overview, ProjectOverview)
    assert overview.plan_count == 0
    assert overview.recent_plans == []


def test_info_never_uses_current_plan(project: Path) -> None:
    seed.plan(project, "auth")
    seed.plan(project, "billing")
    ProjectStateStore(project / ".machi/machinate.toml").write(
        ProjectState(project_name="example", current_plan="billing")
    )
    overview = cli.json(InfoResult, ["info", "-P", str(project), "--format", "json"]).overview
    assert overview.kind == "project"


def test_info_text_smoke(project: Path) -> None:
    result = cli.run(["info", "-P", str(project)])
    assert result.exit_code == 0
    assert "example" in result.stdout


def test_plan_info_overview(project: Path) -> None:
    seed.plan(project, "auth")
    seed.task(project, "auth", "design", status="done")
    seed.task(project, "auth", "implement")
    seed.context(project, "auth", "spec")

    parsed = cli.json(
        PlanInfoResult, ["plan", "info", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.command == "plan info"
    assert isinstance(parsed.overview, PlanOverview)
    overview = parsed.overview
    assert overview.current is False
    assert overview.info.plan.name == "auth"
    assert overview.info.task_counts == {"todo": 1, "in-progress": 0, "done": 1}
    assert overview.info.context_count == 1


def test_plan_info_overview_current(project: Path) -> None:
    seed.plan(project, "auth")
    ProjectStateStore(project / ".machi/machinate.toml").write(
        ProjectState(project_name="example", current_plan="auth")
    )
    overview = cli.json(
        PlanInfoResult, ["plan", "info", "-p", "auth", "-P", str(project), "--format", "json"]
    ).overview
    assert isinstance(overview, PlanOverview)
    assert overview.current is True


def test_plan_info_uses_current_plan_without_flag(project: Path) -> None:
    seed.plan(project, "auth")
    seed.plan(project, "billing")
    ProjectStateStore(project / ".machi/machinate.toml").write(
        ProjectState(project_name="example", current_plan="billing")
    )
    overview = cli.json(
        PlanInfoResult, ["plan", "info", "-P", str(project), "--format", "json"]
    ).overview
    assert overview.info.plan.name == "billing"


def test_plan_info_no_current_plan(project: Path) -> None:
    error = cli.error(["plan", "info", "-P", str(project), "--format", "json"])
    assert error.command == "plan info"


def test_plan_info_text_smoke(project: Path) -> None:
    seed.plan(project, "auth")
    result = cli.run(["plan", "info", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0
    assert "auth" in result.stdout


def test_info_missing_project_directory_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    error = cli.error(["info", "-P", str(missing), "--format", "json"])
    assert error.command == "info"
