import os
import stat
from pathlib import Path

import pytest

from machinate.storage.atomic import atomic_create, atomic_write


def test_atomic_write_failure_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "note.md"
    target.write_bytes(b"original")

    def fail_replace(_self: Path, _target: str) -> None:
        raise PermissionError("replacement denied")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(PermissionError):
        atomic_write(target, b"new")
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_cleanup_failure_adds_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "note.md"
    target.write_bytes(b"original")
    original_error = PermissionError("replacement denied")

    def fail_replace(_self: Path, _target: str) -> None:
        raise original_error

    def fail_unlink(_self: Path, **_kwargs: object) -> None:
        raise PermissionError("cleanup denied")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail_replace)
        patch.setattr(Path, "unlink", fail_unlink)
        with pytest.raises(PermissionError) as error:
            atomic_write(target, b"new")

    assert error.value is original_error
    assert target.read_bytes() == b"original"
    leftover = next(path for path in tmp_path.iterdir() if path.name != "note.md")
    assert str(leftover) in error.value.__notes__[0]
    assert "cleanup denied" in error.value.__notes__[0]
    leftover.unlink()


def test_atomic_create_is_exclusive(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        atomic_create(target, b"new")
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_create_writes_new_file(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "note.md"
    atomic_create(target, b"body")
    assert target.read_bytes() == b"body"
    assert list(target.parent.iterdir()) == [target]


def test_fresh_file_uses_umask_default(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    atomic_write(target, b"body")
    current = os.umask(0)
    os.umask(current)
    assert stat.S_IMODE(target.stat().st_mode) == 0o666 & ~current
