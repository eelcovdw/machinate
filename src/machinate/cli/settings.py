from typing import ClassVar, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type FormatName = Literal["text", "json"]


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_prefix="MACHI_")

    interactive: bool = True
    format: FormatName = "text"

    @model_validator(mode="after")
    def _resolve_format(self) -> Settings:
        if "format" not in self.model_fields_set:
            self.format = "text" if self.interactive else "json"
        return self
