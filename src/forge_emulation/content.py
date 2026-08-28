from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from .models import Game


class ContentError(RuntimeError):
    pass


def materialize_game(game: Game, cache_root: Path) -> Path:
    if not game.archive_member:
        if not game.source_path.is_file():
            raise ContentError(f"Game file is unavailable: {game.source_path}")
        return game.source_path

    member = PurePosixPath(game.archive_member)
    if member.is_absolute() or ".." in member.parts:
        raise ContentError("The selected archive member has an unsafe path.")
    destination_dir = cache_root / game.sha256
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"content{game.extension}"
    if destination.is_file() and destination.stat().st_size == game.size:
        return destination
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        with (
            ZipFile(game.source_path) as archive,
            archive.open(game.archive_member) as source,
            temporary.open("wb") as target,
        ):
            shutil.copyfileobj(source, target, 1024 * 1024)
        if temporary.stat().st_size != game.size:
            raise ContentError("The extracted game size did not match the scanned archive entry.")
        temporary.replace(destination)
    except (BadZipFile, KeyError, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise ContentError(f"Could not extract {game.archive_member}") from exc
    return destination
