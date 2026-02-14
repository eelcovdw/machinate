from pathlib import Path

import pytest

from machinate.plan_service import create_plan
from machinate.project_state import STATE_FILE, ProjectState
from machinate.task_service import TASKS_DIR, add_task, list_tasks


class TestAddTask:
    def test_creates_tasks_dir(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        tasks_dir = add_task(tmp_path, "my-plan")
        assert tasks_dir == tmp_path / "my-plan" / TASKS_DIR
        assert tasks_dir.is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        add_task(tmp_path, "my-plan")
        add_task(tmp_path, "my-plan")
        assert (tmp_path / "my-plan" / TASKS_DIR).is_dir()

    def test_with_filename(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        path = add_task(tmp_path, "my-plan", "auth.md")
        assert path == tmp_path / "my-plan" / TASKS_DIR / "auth.md"
        assert path.exists()

    def test_with_filename_preserves_existing(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        path = add_task(tmp_path, "my-plan", "auth.md")
        path.write_text("hello")
        add_task(tmp_path, "my-plan", "auth.md")
        assert path.read_text() == "hello"

    def test_auto_appends_md_suffix(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        path = add_task(tmp_path, "my-plan", "auth")
        assert path == tmp_path / "my-plan" / TASKS_DIR / "auth.md"
        assert path.exists()

    def test_does_not_double_md_suffix(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        path = add_task(tmp_path, "my-plan", "auth.md")
        assert path == tmp_path / "my-plan" / TASKS_DIR / "auth.md"

    def test_uses_current_plan(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        ProjectState(current_plan="my-plan").save(tmp_path / STATE_FILE)
        tasks_dir = add_task(tmp_path)
        assert tasks_dir == tmp_path / "my-plan" / TASKS_DIR

    def test_raises_when_plan_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            add_task(tmp_path, "nope")


class TestListTasks:
    def test_empty_when_no_tasks_dir(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        assert list_tasks(tmp_path, "my-plan") == []

    def test_empty_when_tasks_dir_empty(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        (tmp_path / "my-plan" / TASKS_DIR).mkdir()
        assert list_tasks(tmp_path, "my-plan") == []

    def test_lists_sorted(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        add_task(tmp_path, "my-plan", "zebra.md")
        add_task(tmp_path, "my-plan", "alpha.md")
        tasks_dir = tmp_path / "my-plan" / TASKS_DIR
        assert list_tasks(tmp_path, "my-plan") == [tasks_dir / "alpha.md", tasks_dir / "zebra.md"]

    def test_uses_current_plan(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        ProjectState(current_plan="my-plan").save(tmp_path / STATE_FILE)
        add_task(tmp_path, "my-plan", "todo.md")
        assert list_tasks(tmp_path) == [tmp_path / "my-plan" / TASKS_DIR / "todo.md"]

    def test_ignores_subdirs(self, tmp_path: Path) -> None:
        create_plan(tmp_path, "my-plan")
        add_task(tmp_path, "my-plan", "real.md")
        (tmp_path / "my-plan" / TASKS_DIR / "subdir").mkdir()
        assert list_tasks(tmp_path, "my-plan") == [tmp_path / "my-plan" / TASKS_DIR / "real.md"]
