"""Read local game media and move explicit selections into recoverable storage."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .paths import AppPaths


def checked_media(path: Path, root: Path) -> str:
    if (
        root.is_symlink()
        or path.is_symlink()
        or not path.is_file()
        or path.parent.resolve() != root.resolve()
        or path.suffix.lower() not in {".state", ".png"}
    ):
        raise ValueError("Select a regular game state or screenshot from this game folder.")
    if path.stat().st_size > 65 * 1024 * 1024:
        raise ValueError("Media file exceeds the supported size limit.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_media(path: Path, root: Path, target: Path) -> None:
    digest = checked_media(path, root)
    with target.open("xb") as output:
        output.write(path.read_bytes())
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        target.unlink()
        raise ValueError("Media changed during export; no export retained.")


def recoverable_remove(paths: AppPaths, path: Path, root: Path, expected_sha256: str) -> Path:
    if checked_media(path, root) != expected_sha256:
        raise ValueError("Media changed after review; refresh and review it again.")
    sources = [path]
    if path.suffix == ".state":
        thumbnail = path.with_suffix(".png")
        if thumbnail.exists() or thumbnail.is_symlink():
            checked_media(thumbnail, root)
            sources.append(thumbnail)
    recovery = paths.backups / "removed-media" / datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    recovery.mkdir(parents=True, exist_ok=False)
    moved: list[tuple[Path, Path]] = []
    try:
        for source in sources:
            destination = recovery / source.name
            shutil.move(str(source), destination)
            moved.append((source, destination))
    except OSError as error:
        failures = []
        for source, destination in reversed(moved):
            try:
                shutil.move(str(destination), source)
            except OSError:
                failures.append(str(destination))
        if failures:
            raise OSError(
                "Removal interrupted; recover remaining files from " + str(recovery)
            ) from error
        recovery.rmdir()
        raise
    return recovery / path.name
