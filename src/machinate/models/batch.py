from pydantic import BaseModel, ValidationError


class BatchCreateError(BaseModel):
    """A name from a batch creation that was not created, with the reason."""

    name: str
    error: str


def first_validation_message(exc: ValidationError) -> str:
    """The single most relevant message from a pydantic validation failure."""
    msg = str(exc.errors()[0]["msg"])
    return msg.removeprefix("Value error, ")
