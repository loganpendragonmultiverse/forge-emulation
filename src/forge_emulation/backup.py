from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .paths import AppPaths

BACKUP_ROOTS = (
    "library.sqlite3",
    "controller-profiles.json",
    "preferences.json",
    "saves",
    "states",
    "screenshots",
    "artwork",
)


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def export_backup(paths: AppPaths, target: Path) -> dict[str, object]:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Snapshot first: SQLite WAL/checkpoints and live saves must not change between
    # checksum calculation and archive writing.
    with tempfile.TemporaryDirectory(prefix="forge-emulation-backup-") as directory:
        staging = Path(directory)
        files: list[dict[str, object]] = []
        for root_name in BACKUP_ROOTS:
            source = paths.userdata / root_name
            candidates = (
                [source] if source.is_file() else source.rglob("*") if source.is_dir() else []
            )
            for file_path in candidates:
                if not file_path.is_file() or file_path.is_symlink():
                    continue
                relative = file_path.relative_to(paths.userdata).as_posix()
                snapshot = staging / relative
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                if root_name == "library.sqlite3":
                    with (
                        closing(sqlite3.connect(file_path)) as origin,
                        closing(sqlite3.connect(snapshot)) as destination,
                    ):
                        origin.backup(destination)
                else:
                    shutil.copyfile(file_path, snapshot)
                files.append(
                    {"path": relative, "size": snapshot.stat().st_size, "sha256": _digest(snapshot)}
                )
        manifest: dict[str, object] = {
            "format": "ForgeEmulation backup",
            "schema": 1,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "files": files,
        }
        temporary = target.with_suffix(target.suffix + ".partial")
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            archive.writestr("forge-backup.json", json.dumps(manifest, indent=2))
            for entry in files:
                relative = str(entry["path"])
                archive.write(staging / relative, relative)
        temporary.replace(target)
    return manifest


def restore_backup(paths: AppPaths, source: Path) -> dict[str, object]:
    with ZipFile(source) as archive:
        try:
            manifest = json.loads(archive.read("forge-backup.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError("This is not a valid ForgeEmulation backup.") from exc
        if not isinstance(manifest, dict) or manifest.get("schema") != 1:
            raise ValueError("This backup format is not supported.")
        entries = manifest.get("files")
        if not isinstance(entries, list):
            raise ValueError("The backup manifest is incomplete.")
        with tempfile.TemporaryDirectory(prefix="forge-emulation-restore-") as temporary:
            staging = Path(temporary)
            validated: list[tuple[Path, Path]] = []
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    raise ValueError("The backup contains an invalid entry.")
                relative = Path(str(entry["path"]))
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or relative.parts[0] not in BACKUP_ROOTS
                ):
                    raise ValueError("The backup contains an unsafe path.")
                destination = (staging / relative).resolve()
                if staging.resolve() not in destination.parents:
                    raise ValueError("The backup contains an unsafe path.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with (
                        archive.open(relative.as_posix()) as input_file,
                        destination.open("wb") as output,
                    ):
                        shutil.copyfileobj(input_file, output)
                except KeyError as exc:
                    raise ValueError(f"Backup file is missing: {relative}") from exc
                if _digest(destination) != entry.get("sha256"):
                    raise ValueError(f"Backup checksum failed: {relative}")
                validated.append((destination, paths.userdata / relative))
            recovery = paths.backups / (
                "pre-restore-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
            )
            export_backup(paths, recovery)
            manifest["pre_restore_backup"] = str(recovery)
            for staged, destination in validated:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged, destination)
    return manifest
