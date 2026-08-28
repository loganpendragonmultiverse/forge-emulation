from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest

from forge_emulation.content import ContentError, materialize_game
from forge_emulation.database import LibraryDatabase
from forge_emulation.scanner import inspect_file


def test_materializes_archive_member(rom_directory: Path, tmp_path: Path) -> None:
    archive_path = tmp_path / "games.zip"
    source = rom_directory / "forge-test.gb"
    with ZipFile(archive_path, "w") as archive:
        archive.write(source, "portable/forge-test.gb")
    candidate = inspect_file(archive_path)[0]
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    database.import_candidates([candidate])
    game = database.list_games()[0]
    extracted = materialize_game(game, tmp_path / "cache")
    assert extracted.read_bytes() == source.read_bytes()


def test_rejects_unsafe_archive_member(rom_directory: Path, tmp_path: Path) -> None:
    candidate = inspect_file(rom_directory / "forge-test.nes")[0]
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    database.import_candidates([candidate])
    game = database.list_games()[0]
    unsafe = replace(game, archive_member="../escape.nes")
    with pytest.raises(ContentError, match="unsafe"):
        materialize_game(unsafe, tmp_path / "cache")
