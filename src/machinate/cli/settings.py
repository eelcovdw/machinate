from typing import ClassVar, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type FormatName = Literal["text", "json"]
type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_prefix="MACHI_")

    interactive: bool = True
    format: FormatName = "text"
    log_level: LogLevel | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _resolve_format(self) -> Settings:
        if "format" not in self.model_fields_set:
            self.format = "text" if self.interactive else "json"
        return self
