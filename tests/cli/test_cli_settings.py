import pytest
from pydantic import ValidationError

from machinate.cli.settings import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_text() -> None:
    settings = Settings()
    assert settings.automation is False
    assert settings.format == "text"


def test_automation_defaults_to_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    settings = Settings()
    assert settings.automation is True
    assert settings.format == "json"


def test_explicit_format_beats_automation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    monkeypatch.setenv("MACHI_FORMAT", "text")
    assert Settings().format == "text"


def test_automation_false_stays_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "false")
    settings = Settings()
    assert settings.automation is False
    assert settings.format == "text"


def test_invalid_automation_reports_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "perhaps")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "automation" in str(excinfo.value)
