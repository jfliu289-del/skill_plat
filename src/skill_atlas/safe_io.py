"""Small, symlink-safe atomic file publication primitives."""

import os
from pathlib import Path
import tempfile
from typing import Optional


class AtomicWriteError(ValueError):
    """Raised when an output target cannot be written without following links."""


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Durably replace one regular file using a random same-directory temp file."""

    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise AtomicWriteError("atomic output parent must be a real directory")
    resolved_parent = parent.resolve()
    if path.is_symlink():
        raise AtomicWriteError("atomic output target must not be a symlink")
    if path.exists() and not path.is_file():
        raise AtomicWriteError("atomic output target must be a regular file")
    if path.resolve(strict=False).parent != resolved_parent:
        raise AtomicWriteError("atomic output target escapes its parent")

    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=parent,
            prefix=f".{path.name}-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            if temporary.is_symlink() or temporary.resolve().parent != resolved_parent:
                raise AtomicWriteError("atomic temporary file escaped its parent")
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise AtomicWriteError("atomic output target became a symlink")
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(parent)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        # Some supported filesystems do not expose directory fsync.
        pass
    finally:
        os.close(descriptor)
