from collections.abc import Mapping
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseModel):
    # Tests build settings by field name; environ is read by its MACHI_* names.
    model_config: ClassVar[ConfigDict] = ConfigDict(validate_by_name=True, extra="ignore")

    # MACHI_AI_AGENT wins over the AI_AGENT convention; the first present variable
    # decides, even when empty. Empty or unset means human mode.
    ai_agent: Annotated[
        str | None, Field(validation_alias=AliasChoices("MACHI_AI_AGENT", "AI_AGENT"))
    ] = None
    # Left unvalidated here so an explicit --format override wins over an invalid
    # MACHI_FORMAT; select_formatter validates the effective name instead.
    format: Annotated[str, Field(validation_alias="MACHI_FORMAT")] = ""
    log_level: Annotated[LogLevel | None, Field(validation_alias="MACHI_LOG_LEVEL")] = None

    @property
    def is_agent_mode(self) -> bool:
        """Whether an agent name was set; no terminal or other fallback."""
        return bool(self.ai_agent)

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _resolve_format(self) -> Self:
        if not self.format:
            self.format = "json" if self.is_agent_mode else "text"
        return self

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> Self:
        """Build settings from an explicit environment mapping."""
        return cls.model_validate(dict(environ))
