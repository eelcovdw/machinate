"""Atomic file replacement for the storage layer."""

import sys
import tempfile
from pathlib import Path


def atomic_write(target: Path, content: bytes, *, mode: int | None = None) -> None:
    """Write content to a sibling temporary file and atomically replace target.

    The temporary file is a sibling of target so replacement stays on the same
    filesystem, and an interrupted write cannot leave a truncated or empty file
    behind. Pass the mode of the file being replaced to preserve permissions;
    fresh files are created 0600 (NamedTemporaryFile is always owner-only).

    Raises OSError when a step fails; any leftover temporary file is removed,
    and a cleanup failure is reported as a note on the primary failure.
    """
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(target)
        temporary = None  # Replacement consumed the temporary file.
    finally:
        if temporary is not None:
            failure = sys.exception()
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                if failure is None:
                    raise
                # Keep the write failure primary, but report the leftover temporary file.
                failure.add_note(f"Could not remove temporary file {temporary}: {exc}")
