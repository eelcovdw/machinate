from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_prefix="MACHI_")

    automation_mode: bool = False
    format: str | None = None

    def formatter_name(self, override: str | None) -> str:
        if override is not None:
            return override
        if self.format is not None:
            return self.format
        return "json" if self.automation_mode else "text"
