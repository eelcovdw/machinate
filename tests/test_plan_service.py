from pathlib import Path

import pytest

from machinate.context_service import CONTEXT_DIR, add_context
from machinate.plan_service import (
    PLAN_FILE,
    InitResult,
    create_plan,
    execute_init,
    get_current_plan,
    get_plans_dir,
    list_plans,
    plan_init,
    set_plan,
    show_plan,
)
from machinate.project_state import STATE_FILE, ProjectState, get_plan_dir, resolve_current_plan
from machinate.settings import Settings
from machinate.skills import install_skills
from machinate.task_service import TASKS_DIR


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    monkeypatch.delenv("MACHINATE_BASE_DIR", raising=False)
    monkeypatch.delenv("MACHINATE_PROJECT", raising=False)
    monkeypatch.delenv("MACHINATE_OBSIDIAN_VAULT", raising=False)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "my-project"
    root.mkdir()
    (root / ".git").mkdir()
    return root


class TestPlanInitExplicitPlansDir:
    def test_resolves_plans_dir(self, tmp_path: Path, project_root: Path) -> None:
        plans = tmp_path / "my-plans"
        result = plan_init(project_root=project_root, plans_dir=plans)
        assert result.plans_dir == plans.resolve()

    def test_symlinks_claude_plans(self, tmp_path: Path, project_root: Path) -> None:
        plans = tmp_path / "my-plans"
        result = plan_init(project_root=project_root, plans_dir=plans)
        assert result.symlink is not None
        assert result.symlink == (project_root / ".claude" / "plans").resolve()


class TestPlanInitBaseDirAndProject:
    def test_base_dir_and_project(self, tmp_path: Path, project_root: Path) -> None:
        result = plan_init(
            project_root=project_root,
            base_plans_dir=tmp_path / "base",
            project_name="foo",
        )
        assert result.plans_dir == (tmp_path / "base" / "foo").resolve()

    def test_base_dir_from_env(
        self,
        tmp_path: Path,
        project_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("MACHINATE_BASE_DIR", str(tmp_path / "env-base"))
        result = plan_init(project_root=project_root, project_name="bar")
        assert result.plans_dir == (tmp_path / "env-base" / "bar").resolve()

    def test_obsidian_vault_from_env(
        self,
        tmp_path: Path,
        project_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("MACHINATE_OBSIDIAN_VAULT", str(tmp_path / "vault"))
        result = plan_init(project_root=project_root, project_name="baz")
        assert result.plans_dir == (tmp_path / "vault" / "machinate" / "baz").resolve()

    def test_base_dir_takes_precedence_over_vault(
        self,
        tmp_path: Path,
        project_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("MACHINATE_BASE_DIR", str(tmp_path / "base"))
        monkeypatch.setenv("MACHINATE_OBSIDIAN_VAULT", str(tmp_path / "vault"))
        result = plan_init(project_root=project_root, project_name="qux")
        assert result.plans_dir == (tmp_path / "base" / "qux").resolve()

    def test_project_name_from_env(
        self,
        tmp_path: Path,
        project_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("MACHINATE_PROJECT", "env-project")
        result = plan_init(
            project_root=project_root,
            base_plans_dir=tmp_path / "base",
        )
        assert result.plans_dir == (tmp_path / "base" / "env-project").resolve()

    def test_project_name_inferred_from_root(self, tmp_path: Path, project_root: Path) -> None:
        result = plan_init(
            project_root=project_root,
            base_plans_dir=tmp_path / "base",
        )
        assert result.plans_dir == (tmp_path / "base" / "my-project").resolve()

    def test_symlinks_claude_plans(self, tmp_path: Path, project_root: Path) -> None:
        result = plan_init(
            project_root=project_root,
            base_plans_dir=tmp_path / "base",
            project_name="foo",
        )
        assert result.symlink is not None
        assert result.symlink.resolve() == (project_root / ".claude" / "plans").resolve()


class TestPlanInitLocalFallback:
    def test_uses_claude_plans_dir(self, project_root: Path) -> None:
        result = plan_init(project_root=project_root)
        expected = (project_root / ".claude" / "plans").resolve()
        assert result.plans_dir == expected

    def test_no_symlink_when_local(self, project_root: Path) -> None:
        result = plan_init(project_root=project_root)
        assert result.symlink is None


class TestPlanInitWithSettings:
    def test_settings_base_dir(self, tmp_path: Path, project_root: Path) -> None:
        settings = Settings(base_dir=tmp_path / "from-settings")
        result = plan_init(
            settings=settings,
            project_root=project_root,
            project_name="proj",
        )
        assert result.plans_dir == (tmp_path / "from-settings" / "proj").resolve()

    def test_settings_obsidian_vault(self, tmp_path: Path, project_root: Path) -> None:
        settings = Settings(obsidian_vault=tmp_path / "vault")
        result = plan_init(
            settings=settings,
            project_root=project_root,
            project_name="proj",
        )
        assert result.plans_dir == (tmp_path / "vault" / "machinate" / "proj").resolve()


class TestExecuteInit:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        root = tmp_path / "project"
        root.mkdir()
        (root / ".git").mkdir()
        return root

    def _init_result(
        self,
        project: Path,
        plans_dir: Path,
        symlink: Path | None = None,
    ) -> InitResult:
        return InitResult(plans_dir=plans_dir, project_root=project, symlink=symlink)

    def test_creates_plans_dir(self, tmp_path: Path, project: Path) -> None:
        plans = tmp_path / "plans"
        execute_init(self._init_result(project, plans))
        assert plans.exists()

    def test_creates_state_file(self, tmp_path: Path, project: Path) -> None:
        plans = tmp_path / "plans"
        execute_init(self._init_result(project, plans))
        state_file = plans / STATE_FILE
        assert state_file.exists()
        state = ProjectState.load(state_file)
        assert state.current_plan is None

    def test_does_not_overwrite_existing_state(self, tmp_path: Path, project: Path) -> None:
        plans = tmp_path / "plans"
        plans.mkdir(parents=True)
        state_file = plans / STATE_FILE
        ProjectState(current_plan="existing").save(state_file)

        execute_init(self._init_result(project, plans))
        state = ProjectState.load(state_file)
        assert state.current_plan == "existing"

    def test_creates_symlink(self, tmp_path: Path, project: Path) -> None:
        plans = tmp_path / "plans"
        symlink = tmp_path / "link" / ".claude" / "plans"
        execute_init(self._init_result(project, plans, symlink))
        assert symlink.is_symlink()
        assert symlink.resolve() == plans.resolve()

    def test_skips_existing_symlink(self, tmp_path: Path, project: Path) -> None:
        plans = tmp_path / "plans"
        plans.mkdir(parents=True)
        symlink = tmp_path / "link" / ".claude" / "plans"
        symlink.parent.mkdir(parents=True)
        symlink.symlink_to(plans)

        execute_init(self._init_result(project, plans, symlink))
        assert symlink.is_symlink()

    def test_override_replaces_state(self, tmp_path: Path, project: Path) -> None:
        plans = tmp_path / "plans"
        plans.mkdir(parents=True)
        state_file = plans / STATE_FILE
        ProjectState(current_plan="existing").save(state_file)

        execute_init(self._init_result(project, plans), override=True)
        state = ProjectState.load(state_file)
        assert state.current_plan is None

    def test_moves_existing_dir_to_plans_dir(self, tmp_path: Path, project: Path) -> None:
        plans = tmp_path / "plans"
        symlink = tmp_path / "link" / ".claude" / "plans"
        symlink.mkdir(parents=True)
        (symlink / "some-plan").mkdir()
        (symlink / "some-plan" / "plan.md").write_text("hello")

        execute_init(self._init_result(project, plans, symlink))
        assert symlink.is_symlink()
        assert symlink.resolve() == plans.resolve()
        assert (plans / "some-plan" / "plan.md").read_text() == "hello"

    def test_override_replaces_symlink(self, tmp_path: Path, project: Path) -> None:
        old_target = tmp_path / "old"
        old_target.mkdir()
        new_target = tmp_path / "new"
        symlink = tmp_path / "link" / ".claude" / "plans"
        symlink.parent.mkdir(parents=True)
        symlink.symlink_to(old_target)

        execute_init(self._init_result(project, new_target, symlink), override=True)
        assert symlink.resolve() == new_target.resolve()

    def test_installs_skills(self, project: Path) -> None:
        install_skills(project)
        skills_dir = project / ".claude" / "skills"
        assert skills_dir.is_dir()
        assert (skills_dir / "machinate-plan" / "SKILL.md").exists()
        assert (skills_dir / "machinate-resume" / "SKILL.md").exists()
        assert (skills_dir / "machinate-update" / "SKILL.md").exists()

    def test_installs_skills_idempotent(self, project: Path) -> None:
        install_skills(project)
        # Modify a skill file
        skill_file = project / ".claude" / "skills" / "machinate-plan" / "SKILL.md"
        skill_file.write_text("modified")
        # Re-run overwrites it
        install_skills(project)
        assert skill_file.read_text() != "modified"

    def test_skill_files_use_machi_executable(self, project: Path) -> None:
        install_skills(project)
        for name in ("machinate-plan", "machinate-resume", "machinate-update"):
            content = (project / ".claude" / "skills" / name / "SKILL.md").read_text()
            assert "uv run" not in content
            assert "machi" in content


class TestGetPlansDir:
    def test_returns_plans_dir(self, project_root: Path) -> None:
        plans = project_root / ".claude" / "plans"
        plans.mkdir(parents=True)
        assert get_plans_dir(project_root) == plans

    def test_raises_when_not_initialized(self, project_root: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Not initialized"):
            get_plans_dir(project_root)


class TestCreatePlan:
    def test_creates_plan_dir(self, tmp_path: Path) -> None:
        plan_dir = create_plan(tmp_path, "my-feature")
        assert plan_dir == tmp_path / "my-feature"
        assert plan_dir.is_dir()

    def test_creates_plan_md(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-feature")
        plan_file = tmp_path / "my-feature" / PLAN_FILE
        assert plan_file.exists()
        content = plan_file.read_text()
        assert content.startswith("---\n")
        assert "# Plan: my-feature\n" in content

    def test_raises_when_plan_exists(self, tmp_path: Path) -> None:
        (tmp_path / "existing").mkdir()
        with pytest.raises(FileExistsError, match="already exists"):
            create_plan(tmp_path, "existing")

    def test_exist_ok(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-feature")
        plan_dir = create_plan(tmp_path, "my-feature", exist_ok=True)
        assert plan_dir == tmp_path / "my-feature"


class TestGetPlanDir:
    def test_returns_plan_dir(self, tmp_path: Path) -> None:
        (tmp_path / "my-plan").mkdir()
        assert get_plan_dir(tmp_path, "my-plan") == tmp_path / "my-plan"

    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            get_plan_dir(tmp_path, "nope")


class TestAddContext:
    def test_creates_context_dir(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        context_dir = add_context(tmp_path, "my-plan")
        assert context_dir == tmp_path / "my-plan" / CONTEXT_DIR
        assert context_dir.is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        add_context(tmp_path, "my-plan")
        add_context(tmp_path, "my-plan")
        assert (tmp_path / "my-plan" / CONTEXT_DIR).is_dir()

    def test_with_filename(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        path = add_context(tmp_path, "my-plan", "notes.md")
        assert path == tmp_path / "my-plan" / CONTEXT_DIR / "notes.md"
        assert path.exists()

    def test_with_filename_preserves_existing(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        path = add_context(tmp_path, "my-plan", "notes.md")
        path.write_text("hello")
        add_context(tmp_path, "my-plan", "notes.md")
        assert path.read_text() == "hello"

    def test_auto_appends_md_suffix(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        path = add_context(tmp_path, "my-plan", "notes")
        assert path == tmp_path / "my-plan" / CONTEXT_DIR / "notes.md"
        assert path.exists()

    def test_does_not_double_md_suffix(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        path = add_context(tmp_path, "my-plan", "notes.md")
        assert path == tmp_path / "my-plan" / CONTEXT_DIR / "notes.md"

    def test_uses_current_plan(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        ProjectState(current_plan="my-plan").save(tmp_path / STATE_FILE)
        context_dir = add_context(tmp_path)
        assert context_dir == tmp_path / "my-plan" / CONTEXT_DIR

    def test_raises_when_plan_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            add_context(tmp_path, "nope")


class TestResolveCurrentPlan:
    def test_returns_explicit_name(self, tmp_path: Path) -> None:
        assert resolve_current_plan(tmp_path, "foo") == "foo"

    def test_returns_current_plan(self, tmp_path: Path) -> None:
        ProjectState(current_plan="bar").save(tmp_path / STATE_FILE)
        assert resolve_current_plan(tmp_path) == "bar"

    def test_raises_when_no_current(self, tmp_path: Path) -> None:
        ProjectState().save(tmp_path / STATE_FILE)
        with pytest.raises(ValueError, match="No current plan"):
            resolve_current_plan(tmp_path)


class TestGetCurrentPlan:
    def test_returns_current(self, tmp_path: Path) -> None:
        ProjectState(current_plan="baz").save(tmp_path / STATE_FILE)
        assert get_current_plan(tmp_path) == "baz"

    def test_returns_none(self, tmp_path: Path) -> None:
        ProjectState().save(tmp_path / STATE_FILE)
        assert get_current_plan(tmp_path) is None


class TestListPlans:
    def test_empty(self, tmp_path: Path) -> None:
        assert list_plans(tmp_path) == []

    def test_lists_plans_sorted(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "zebra")
        create_plan(tmp_path, "alpha")
        assert list_plans(tmp_path) == ["alpha", "zebra"]

    def test_ignores_non_plan_dirs(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "real-plan")
        (tmp_path / "random-dir").mkdir()  # no plan.md
        assert list_plans(tmp_path) == ["real-plan"]


class TestSetPlan:
    def test_sets_current_plan(self, tmp_path: Path) -> None:
        ProjectState().save(tmp_path / STATE_FILE)
        create_plan(tmp_path, "my-plan")
        set_plan(tmp_path, "my-plan")
        state = ProjectState.load(tmp_path / STATE_FILE)
        assert state.current_plan == "my-plan"

    def test_raises_when_plan_not_found(self, tmp_path: Path) -> None:
        ProjectState().save(tmp_path / STATE_FILE)
        with pytest.raises(FileNotFoundError, match="not found"):
            set_plan(tmp_path, "nope")


class TestShowPlan:
    def test_shows_plan_by_name(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        info = show_plan(tmp_path, "my-plan")
        assert info.name == "my-plan"
        assert info.plan_dir == tmp_path / "my-plan"
        assert "# Plan: my-plan\n" in info.plan_content
        assert info.task_files == []
        assert info.context_files == []

    def test_shows_current_plan(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        ProjectState(current_plan="my-plan").save(tmp_path / STATE_FILE)
        info = show_plan(tmp_path)
        assert info.name == "my-plan"

    def test_raises_when_no_current_plan(self, tmp_path: Path) -> None:
        ProjectState().save(tmp_path / STATE_FILE)
        with pytest.raises(ValueError, match="No current plan"):
            show_plan(tmp_path)

    def test_detects_tasks(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        tasks = tmp_path / "my-plan" / TASKS_DIR
        tasks.mkdir()
        (tasks / "setup.md").write_text("do stuff\n")
        info = show_plan(tmp_path, "my-plan")
        assert info.task_files == [tasks / "setup.md"]

    def test_detects_context_files(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        ctx = tmp_path / "my-plan" / CONTEXT_DIR
        ctx.mkdir()
        (ctx / "notes.md").write_text("hello")
        (ctx / "spec.md").write_text("world")
        info = show_plan(tmp_path, "my-plan")
        assert info.context_files == [ctx / "notes.md", ctx / "spec.md"]
