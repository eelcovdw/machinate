from pathlib import Path

import pytest

from machinate.settings import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    monkeypatch.delenv("MACHINATE_BASE_DIR", raising=False)
    monkeypatch.delenv("MACHINATE_PROJECT", raising=False)
    monkeypatch.delenv("MACHINATE_OBSIDIAN_VAULT", raising=False)


class TestSettings:
    def test_defaults_are_none(self) -> None:
        settings = Settings()
        assert settings.base_dir is None
        assert settings.project is None
        assert settings.obsidian_vault is None

    def test_base_dir_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MACHINATE_BASE_DIR", "/tmp/plans")  # noqa: S108
        settings = Settings()
        assert settings.base_dir == Path("/tmp/plans")  # noqa: S108

    def test_project_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MACHINATE_PROJECT", "my-project")
        settings = Settings()
        assert settings.project == "my-project"

    def test_obsidian_vault_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MACHINATE_OBSIDIAN_VAULT", "/tmp/vault")  # noqa: S108
        settings = Settings()
        assert settings.obsidian_vault == Path("/tmp/vault")  # noqa: S108
