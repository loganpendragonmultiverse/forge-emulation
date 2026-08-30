from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from forge_emulation.database import LibraryDatabase
from forge_emulation.scanner import inspect_file, scan_paths


def test_scans_files_and_deduplicates_content(rom_directory: Path, tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.nes"
    duplicate.write_bytes((rom_directory / "forge-test.nes").read_bytes())
    games, errors = scan_paths([rom_directory, duplicate])
    assert errors == []
    assert {game.system_id for game in games} == {
        "nes",
        "snes",
        "gb",
        "gbc",
        "genesis",
        "gba",
        "sms",
        "gamegear",
        "atari2600",
    }
    assert len(games) == 9


def test_scans_supported_members_inside_zip(rom_directory: Path, tmp_path: Path) -> None:
    archive_path = tmp_path / "library.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.write(rom_directory / "forge-test.gbc", "games/forge-test.gbc")
        archive.writestr("notes.txt", "not a game")
    candidates = inspect_file(archive_path)
    assert len(candidates) == 1
    assert candidates[0].system_id == "gbc"
    assert candidates[0].archive_member == "games/forge-test.gbc"


def test_database_library_workflow(rom_directory: Path, tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    games, errors = scan_paths([rom_directory])
    assert errors == []
    assert database.import_candidates(games) == (9, 9)
    assert database.import_candidates(games) == (0, 9)

    nes = database.list_games(system_id="nes")[0]
    database.set_favorite(nes.id, True)
    assert database.list_games(favorites_only=True)[0].id == nes.id
    assert database.list_games(query="FORGE")[0].title == "forge-test"

    database.record_session(
        game_id=nes.id,
        started_at="2026-08-27T12:00:00+00:00",
        ended_at="2026-08-27T12:02:00+00:00",
        duration_seconds=120,
        core_filename="nestopia_libretro.dll",
        core_version="test",
        exit_reason="user-exit",
    )
    updated = database.get_game(nes.id)
    assert updated is not None
    assert updated.playtime_seconds == 120
    assert updated.session_count == 1
