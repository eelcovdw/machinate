"""Atomic file operations for the storage layer."""

import os
import sys
import tempfile
from pathlib import Path


def _umask_default_mode() -> int:
    """Return the mode a fresh file gets under the current umask (0666 & ~umask)."""
    current = os.umask(0)
    os.umask(current)
    return 0o666 & ~current


def _cleanup(temporary: Path | None, failure: BaseException | None) -> None:
    """Remove a leftover temporary file, adding a note if the primary failure survives."""
    if temporary is None:
        return
    try:
        temporary.unlink(missing_ok=True)
    except OSError as exc:
        if failure is None:
            raise
        failure.add_note(f"Could not remove temporary file {temporary}: {exc}")


def atomic_write(target: Path, content: bytes, *, mode: int | None = None) -> None:
    """Write content to a sibling temporary file and atomically replace target.

    The temporary file is a sibling of target so replacement stays on the same
    filesystem, and a process crash cannot leave a truncated or empty file behind.
    This does not fsync, so a power loss or kernel crash can still lose the write.
    Replacement drops ownership, xattrs/ACLs, and hard links (inherent to rename).
    Pass the mode of the file being replaced to preserve permissions; fresh files
    use the umask default (the process is the only writer here, not a secret store).

    Raises OSError when a step fails; any leftover temporary file is removed,
    and a cleanup failure is reported as a note on the primary failure.
    """
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.chmod(mode if mode is not None else _umask_default_mode())
        temporary.replace(target)
        temporary = None  # Replacement consumed the temporary file.
    finally:
        _cleanup(temporary, sys.exception())


def atomic_create(target: Path, content: bytes) -> None:
    """Create target exclusively by writing a temporary sibling and hard-linking it.

    ``os.link`` fails with ``FileExistsError`` when target already exists, so an
    interrupted create cannot leave a truncated document behind. The temporary file
    is removed on every path.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    failure: BaseException | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.chmod(_umask_default_mode())
        os.link(temporary, target)
    except BaseException as exc:
        failure = exc
        raise
    finally:
        _cleanup(temporary, failure)
