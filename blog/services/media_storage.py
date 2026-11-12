import os
import shutil
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from django.core.files import File
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management.base import CommandError


def clean_name(name):
    """Return one storage-relative POSIX path or reject an unsafe name."""
    path = PurePosixPath(str(name).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise CommandError(f"Unsafe media path: {name}")
    return path.as_posix()


def walk_files(storage=None, prefix="") -> Iterator[str]:
    """Yield files from any Django storage without requiring local paths."""
    storage = storage or default_storage
    prefix = clean_name(prefix).strip("/") if prefix else ""
    if isinstance(storage, FileSystemStorage):
        base = Path(storage.location).resolve()
        start = (base / prefix).resolve()
        try:
            start.relative_to(base)
        except ValueError as exc:
            raise CommandError(f"Unsafe media prefix: {prefix}") from exc
        if not start.exists():
            return
        for root, directories, files in os.walk(start, followlinks=False):
            root_path = Path(root)
            directories[:] = [
                name for name in directories if not (root_path / name).is_symlink()
            ]
            for name in files:
                path = root_path / name
                if not path.is_symlink():
                    yield path.relative_to(base).as_posix()
        return
    pending = [prefix]
    visited = set()
    while pending:
        folder = pending.pop()
        if folder in visited:
            continue
        visited.add(folder)
        try:
            directories, files = storage.listdir(folder)
        except (FileNotFoundError, OSError):
            continue
        for name in files:
            yield clean_name(f"{folder}/{name}" if folder else name)
        for name in directories:
            child = clean_name(f"{folder}/{name}" if folder else name).rstrip("/")
            if child and child not in visited:
                pending.append(child)


def is_local(storage=None):
    return isinstance(storage or default_storage, FileSystemStorage)


def local_name(storage, path):
    """Map a local file to a storage key, returning None when it is outside."""
    if not isinstance(storage, FileSystemStorage):
        return None
    try:
        return path.resolve().relative_to(Path(storage.location).resolve()).as_posix()
    except ValueError:
        return None


def save_exact(storage, name, source):
    """Save a key without silently accepting a renamed object."""
    name = clean_name(name)
    saved = storage.save(name, source)
    if saved == name:
        return
    try:
        storage.delete(saved)
    finally:
        raise CommandError(
            f"Storage renamed {name} to {saved}; restore cannot preserve references."
        )


def restore_directory(source_root, storage=None, rollback_root=None):
    """Copy staged media into a remote storage and return rollback information."""
    storage = storage or default_storage
    source_root = Path(source_root)
    rollback_root = Path(rollback_root or source_root.parent / "storage-rollback")
    changes = []
    try:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            name = clean_name(path.relative_to(source_root).as_posix())
            previous = None
            if storage.exists(name):
                previous = rollback_root / name
                previous.parent.mkdir(parents=True, exist_ok=True)
                with storage.open(name, "rb") as remote, previous.open("xb") as local:
                    shutil.copyfileobj(remote, local, length=1024 * 1024)
                storage.delete(name)
            changes.append((name, previous))
            with path.open("rb") as source:
                save_exact(storage, name, File(source, name=name))
    except Exception:
        rollback_storage(changes, storage)
        raise
    return changes


def rollback_storage(changes, storage=None):
    storage = storage or default_storage
    for name, previous in reversed(changes):
        storage.delete(name)
        if previous and previous.exists():
            with previous.open("rb") as old:
                save_exact(storage, name, File(old, name=name))
