from pathlib import Path

from machinate.project_state import ProjectState


class TestLoad:
    def test_missing_file_returns_default(self, tmp_path: Path) -> None:
        state = ProjectState.load(tmp_path / "machinate.toml")
        assert state.current_plan is None

    def test_loads_current_plan(self, tmp_path: Path) -> None:
        path = tmp_path / "machinate.toml"
        path.write_text('current_plan = "my-plan"\n')
        state = ProjectState.load(path)
        assert state.current_plan == "my-plan"


class TestSave:
    def test_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "machinate.toml"
        ProjectState(current_plan="my-plan").save(path)
        assert path.exists()
        state = ProjectState.load(path)
        assert state.current_plan == "my-plan"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "machinate.toml"
        ProjectState(current_plan="my-plan").save(path)
        assert path.exists()

    def test_excludes_none_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "machinate.toml"
        ProjectState().save(path)
        assert path.read_text() == ""


class TestRoundtrip:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "machinate.toml"
        original = ProjectState(current_plan="auth-refactor")
        original.save(path)
        loaded = ProjectState.load(path)
        assert loaded == original

    def test_overwrite(self, tmp_path: Path) -> None:
        path = tmp_path / "machinate.toml"
        ProjectState(current_plan="first").save(path)
        ProjectState(current_plan="second").save(path)
        loaded = ProjectState.load(path)
        assert loaded.current_plan == "second"
