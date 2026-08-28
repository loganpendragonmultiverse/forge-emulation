from __future__ import annotations

import hashlib
import re
import zlib
from collections.abc import Callable, Iterable
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .models import GameCandidate
from .systems import accepted_file, detect_system

MAX_ARCHIVE_MEMBER_SIZE = 128 * 1024 * 1024
READ_CHUNK = 1024 * 1024


class ScanError(RuntimeError):
    pass


def _clean_title(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_\.]+", " ", stem)
    stem = re.sub(r"\s*\([^)]*\)\s*", " ", stem)
    stem = re.sub(r"\s*\[[^]]*]\s*", " ", stem)
    return re.sub(r"\s+", " ", stem).strip() or Path(filename).stem


def _candidate(
    *,
    filename: str,
    source_path: Path,
    archive_member: str | None,
    chunks: Iterable[bytes],
    declared_size: int,
) -> GameCandidate | None:
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1()  # noqa: S324 - required for established ROM databases
    crc = 0
    header = bytearray()
    actual_size = 0
    for chunk in chunks:
        actual_size += len(chunk)
        sha256.update(chunk)
        sha1.update(chunk)
        crc = zlib.crc32(chunk, crc)
        if len(header) < 0x410200:
            header.extend(chunk[: 0x410200 - len(header)])
    size = actual_size or declared_size
    detected = detect_system(filename, bytes(header), size)
    if detected is None:
        return None
    system_id, method = detected
    digest = sha256.hexdigest()
    return GameCandidate(
        game_id=f"{system_id}:{digest}",
        title=_clean_title(filename),
        system_id=system_id,
        source_path=source_path.resolve(),
        archive_member=archive_member,
        size=size,
        sha256=digest,
        sha1=sha1.hexdigest(),
        crc32=f"{crc & 0xFFFFFFFF:08x}",
        extension=Path(filename).suffix.lower(),
        detection=method,
    )


def inspect_file(path: Path) -> list[GameCandidate]:
    if path.suffix.lower() == ".zip":
        return _inspect_archive(path)
    with path.open("rb") as handle:
        candidate = _candidate(
            filename=path.name,
            source_path=path,
            archive_member=None,
            chunks=iter(lambda: handle.read(READ_CHUNK), b""),
            declared_size=path.stat().st_size,
        )
    return [candidate] if candidate else []


def _inspect_archive(path: Path) -> list[GameCandidate]:
    candidates: list[GameCandidate] = []
    try:
        with ZipFile(path) as archive:
            for info in archive.infolist():
                member_path = Path(info.filename)
                if info.is_dir() or member_path.suffix.lower() == ".zip":
                    continue
                if not accepted_file(member_path) or info.file_size > MAX_ARCHIVE_MEMBER_SIZE:
                    continue
                with archive.open(info) as handle:
                    candidate = _candidate(
                        filename=member_path.name,
                        source_path=path,
                        archive_member=info.filename,
                        chunks=iter(lambda: handle.read(READ_CHUNK), b""),
                        declared_size=info.file_size,
                    )
                if candidate:
                    candidates.append(candidate)
    except (BadZipFile, OSError) as exc:
        raise ScanError(f"Could not inspect archive: {path}") from exc
    return candidates


def scan_paths(
    paths: Iterable[Path],
    progress: Callable[[Path], None] | None = None,
) -> tuple[list[GameCandidate], list[str]]:
    games: dict[str, GameCandidate] = {}
    errors: list[str] = []
    for selected in paths:
        selected = selected.expanduser().resolve()
        inputs = (
            (path for path in selected.rglob("*") if path.is_file() and accepted_file(path))
            if selected.is_dir()
            else (selected,)
        )
        for path in inputs:
            if not path.is_file() or not accepted_file(path):
                continue
            if progress:
                progress(path)
            try:
                for game in inspect_file(path):
                    games.setdefault(game.game_id, game)
            except (OSError, ScanError) as exc:
                errors.append(str(exc))
    return list(games.values()), errors
