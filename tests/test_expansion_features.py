from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from forge_emulation.artwork import install_artwork
from forge_emulation.backup import export_backup, restore_backup
from forge_emulation.database import LibraryDatabase
from forge_emulation.diagnostics import build_diagnostics, diagnostic_text
from forge_emulation.paths import app_paths
from forge_emulation.scanner import scan_paths
from forge_emulation.settings import RuntimeSettings, SettingsStore


def test_settings_global_and_game_overrides(tmp_path: Path) -> None:
    target = tmp_path / "preferences.json"
    store = SettingsStore(target)
    store.set_global(
        RuntimeSettings(
            fullscreen=True,
            scaling="integer",
            video_filter="smooth",
            volume=72,
            muted=True,
            state_slot=4,
        )
    )
    store.set_game_override("game", {"volume": 33, "state_slot": 9})
    loaded = SettingsStore(target)
    assert loaded.for_game("game").volume == 33
    assert loaded.for_game("game").state_slot == 9
    assert loaded.for_game("other").scaling == "integer"
    loaded.set_game_override("game", None)
    assert "game" not in SettingsStore(target).game_overrides


def test_settings_normalizes_invalid_and_ignores_bad_files(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        scaling="bad", video_filter="bad", volume=900, state_slot=-2
    ).normalized()
    assert (settings.scaling, settings.video_filter, settings.volume, settings.state_slot) == (
        "fit",
        "nearest",
        100,
        1,
    )
    target = tmp_path / "preferences.json"
    target.write_text("not json", encoding="utf-8")
    assert SettingsStore(target).global_settings == RuntimeSettings()
    target.write_text("[]", encoding="utf-8")
    assert SettingsStore(target).game_overrides == {}


def test_artwork_install_validation(tmp_path: Path) -> None:
    source = tmp_path / "cover.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(16))
    installed = install_artwork(source, tmp_path / "artwork", "game")
    assert installed.read_bytes() == source.read_bytes()
    replacement = tmp_path / "replacement.jpg"
    replacement.write_bytes(b"\xff\xd8\xff" + bytes(16))
    second = install_artwork(replacement, tmp_path / "artwork", "game")
    assert second.suffix == ".jpg"
    assert not installed.exists()
    invalid = tmp_path / "bad.png"
    invalid.write_bytes(b"wrong")
    with pytest.raises(ValueError, match="valid image"):
        install_artwork(invalid, tmp_path / "artwork", "bad")
    with pytest.raises(ValueError, match="Choose"):
        install_artwork(tmp_path / "absent.gif", tmp_path / "artwork", "bad")


def test_backup_round_trip_and_rejects_unsafe_archive(tmp_path: Path) -> None:
    paths = app_paths(tmp_path / "portable")
    paths.preferences.write_text('{"schema": 1}', encoding="utf-8")
    save = paths.saves / "nes" / "game" / "save.srm"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"save-data")
    database = LibraryDatabase(paths.database)
    assert database.integrity_check() == "ok"
    target = tmp_path / "backup.zip"
    manifest = export_backup(paths, target)
    files = manifest["files"]
    assert isinstance(files, list) and len(files) >= 3
    save.write_bytes(b"changed")
    restore_backup(paths, target)
    assert save.read_bytes() == b"save-data"

    unsafe = tmp_path / "unsafe.zip"
    bad_manifest = {
        "schema": 1,
        "files": [{"path": "../escape", "sha256": "bad"}],
    }
    with ZipFile(unsafe, "w") as archive:
        archive.writestr("forge-backup.json", json.dumps(bad_manifest))
    with pytest.raises(ValueError, match="unsafe"):
        restore_backup(paths, unsafe)


def test_database_metadata_recents_and_diagnostics(rom_directory: Path, tmp_path: Path) -> None:
    paths = app_paths(tmp_path / "portable")
    database = LibraryDatabase(paths.database)
    candidates, errors = scan_paths([rom_directory])
    assert errors == []
    database.import_candidates(candidates)
    game = database.list_games()[0]
    artwork = paths.artwork / "cover.png"
    artwork.write_bytes(b"\x89PNG\r\n\x1a\n")
    database.set_metadata(game.id, custom_title="Custom", artwork_path=artwork)
    updated = database.get_game(game.id)
    assert updated and updated.display_title == "Custom" and updated.artwork_path == artwork
    assert database.list_games(query="Custom")[0].id == game.id
    assert database.recent_games() == []
    database.record_session(
        game_id=game.id,
        started_at="2026-08-29T10:00:00+00:00",
        ended_at="2026-08-29T10:01:00+00:00",
        duration_seconds=60,
        core_filename="test.dll",
        core_version="test",
        exit_reason="normal",
    )
    assert database.recent_games(limit=1)[0].id == game.id
    report = build_diagnostics(paths, database)
    assert report["database_integrity"] == "ok"
    assert report["library_games"] == 9
    assert "Custom" not in diagnostic_text(paths, database)
