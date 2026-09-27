from typing import ClassVar, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_prefix="MACHI_")

    automation: bool = False
    # Left unvalidated here so an explicit --format override wins over an invalid
    # MACHI_FORMAT; select_formatter validates the effective name instead.
    format: str = "text"
    log_level: LogLevel | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _resolve_format(self) -> Settings:
        if "format" not in self.model_fields_set:
            self.format = "json" if self.automation else "text"
        return self
