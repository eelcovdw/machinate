from collections.abc import Mapping
from typing import Annotated, ClassVar, Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .formatting import OutputFormat


class Settings(BaseModel):
    # Tests build settings by field name; environ is read by its MACHI_* names.
    model_config: ClassVar[ConfigDict] = ConfigDict(validate_by_name=True, extra="ignore")

    # MACHI_AI_AGENT wins over the AI_AGENT convention; the first present variable
    # decides, even when empty. Empty or unset means human mode.
    ai_agent: Annotated[
        str | None, Field(validation_alias=AliasChoices("MACHI_AI_AGENT", "AI_AGENT"))
    ] = None
    format: Annotated[OutputFormat | None, Field(validation_alias="MACHI_FORMAT")] = None

    @property
    def is_agent_mode(self) -> bool:
        """Whether an agent name was set; no terminal or other fallback."""
        return bool(self.ai_agent)

    @property
    def output_format(self) -> OutputFormat:
        """The effective format: the explicit value, or the agent-aware default."""
        return (
            self.format if self.format is not None else ("json" if self.is_agent_mode else "text")
        )

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> Self:
        """Build settings from the declared aliases only, ignoring lowercase field names."""
        return cls.model_validate(dict(environ), by_alias=True, by_name=False)
