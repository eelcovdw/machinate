from pydantic import ValidationError


class InputError(Exception):
    """Raised when CLI options are missing, contradictory, or otherwise unusable."""


def describe_error(exc: Exception) -> str:
    """Render an exception as a concise, actionable CLI message."""
    if not isinstance(exc, ValidationError):
        return str(exc)
    model = exc.title or "input"
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or model}: {error['msg']}"
        for error in exc.errors()
    )
    return f"Invalid {model}: {details}"
