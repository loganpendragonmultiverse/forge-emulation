from __future__ import annotations

import shutil
from dataclasses import replace

import pytest

from forge_emulation.database import LibraryDatabase
from forge_emulation.media_manager import checked_media, export_media, recoverable_remove
from forge_emulation.paths import app_paths
from forge_emulation.relink import apply_relink, preview_relink
from forge_emulation.scanner import scan_paths


def test_relink_adds_verified_location_preserves_library_and_files(rom_directory, tmp_path):
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    database.import_candidates(scan_paths([rom_directory])[0])
    game = database.list_games(system_id="nes")[0]
    database.set_favorite(game.id, True)
    replacement = tmp_path / "moved"
    replacement.mkdir()
    target = replacement / "new name.nes"
    shutil.copyfile(game.source_path, target)
    original = game.source_path.read_bytes()
    plan = preview_relink(database, replacement)
    assert len(plan.matches) == 1 and len(database.location_records()) == 9
    assert apply_relink(database, plan) == 1
    assert len(database.list_games()) == 9 and database.get_game(game.id).favorite
    assert database.get_game(game.id).source_path == target
    assert game.source_path.read_bytes() == original and target.read_bytes() == original
    with pytest.raises(ValueError):
        apply_relink(database, plan)  # Revision changed.


def test_relink_changed_content_and_incomplete_scans_refuse_all_writes(rom_directory, tmp_path):
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    database.import_candidates(scan_paths([rom_directory])[0])
    replacement = tmp_path / "replacement"
    shutil.copytree(rom_directory, replacement)
    plan = preview_relink(database, replacement)
    with pytest.raises(ValueError):
        apply_relink(database, replace(plan, errors=("Unreadable child",)))
    target = plan.matches[-1].source_path
    target.write_bytes(b"corrupt")
    with pytest.raises((ValueError, OSError)):
        apply_relink(database, plan)
    assert len(database.location_records()) == 9
    with pytest.raises(ValueError):
        preview_relink(database, tmp_path / "absent")


def test_media_exports_and_recovery_are_bound_and_revision_checked(tmp_path):
    paths = app_paths(tmp_path)
    root = paths.states / "nes" / "fixture"
    root.mkdir(parents=True)
    state = root / "slot-1.state"
    state.write_bytes(b"original")
    thumbnail = root / "slot-1.png"
    thumbnail.write_bytes(b"image")
    digest = checked_media(state, root)
    export_media(state, root, tmp_path / "export.state")
    with pytest.raises(FileExistsError):
        export_media(state, root, tmp_path / "export.state")
    with pytest.raises(ValueError):
        recoverable_remove(paths, state, root, "wrong")
    assert state.exists()
    saved = recoverable_remove(paths, state, root, digest)
    assert saved.read_bytes() == b"original" and not state.exists()
    assert saved.with_suffix(".png").read_bytes() == b"image"
    with pytest.raises(ValueError):
        checked_media(saved, root)
    invalid = root / "notes.txt"
    invalid.write_text("not media")
    with pytest.raises(ValueError):
        checked_media(invalid, root)


def test_media_prevalidates_companions_and_rolls_back_failed_moves(tmp_path, monkeypatch):
    paths = app_paths(tmp_path)
    root = paths.states / "nes" / "fixture"
    root.mkdir(parents=True)
    state = root / "slot-1.state"
    state.write_bytes(b"original")
    thumbnail = root / "slot-1.png"
    thumbnail.mkdir()
    digest = checked_media(state, root)
    with pytest.raises(ValueError):
        recoverable_remove(paths, state, root, digest)
    assert state.read_bytes() == b"original"
    thumbnail.rmdir()
    thumbnail.write_bytes(b"image")
    move = shutil.move

    def fail_thumbnail(source, target):
        if str(source) == str(thumbnail):
            raise OSError("simulated unavailable companion")
        return move(source, target)

    monkeypatch.setattr(shutil, "move", fail_thumbnail)
    with pytest.raises(OSError):
        recoverable_remove(paths, state, root, digest)
    assert state.read_bytes() == b"original" and thumbnail.read_bytes() == b"image"
