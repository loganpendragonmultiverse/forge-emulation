from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from forge_emulation.content import ContentError, materialize_game
from forge_emulation.database import LibraryDatabase
from forge_emulation.launch import GameLauncher, LaunchError
from forge_emulation.paths import app_paths, application_root
from forge_emulation.scanner import inspect_file


def _game_from_rom(rom_path: Path, database_path: Path):  # type: ignore[no-untyped-def]
    candidate = inspect_file(rom_path)[0]
    database = LibraryDatabase(database_path)
    database.import_candidates([candidate])
    return database.list_games()[0]


def test_paths_create_private_data_directories(tmp_path: Path) -> None:
    paths = app_paths(tmp_path / "portable")
    assert paths.database.parent == paths.userdata
    assert paths.cores.is_dir()
    assert paths.logs.is_dir()
    assert paths.saves.is_dir()
    assert paths.states.is_dir()
    assert paths.screenshots.is_dir()
    assert paths.cache.is_dir()
    assert paths.controller_profiles == paths.userdata / "controller-profiles.json"


def test_frozen_paths_keep_cores_internal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("forge_emulation.paths.sys.frozen", True, raising=False)
    paths = app_paths(tmp_path / "portable")
    assert paths.cores == (tmp_path / "portable" / "_internal" / "cores").resolve()


def test_application_root_honors_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FORGE_EMULATION_ROOT", str(tmp_path))
    assert application_root() == tmp_path.resolve()


def test_launcher_prepares_isolated_runtime_config(rom_directory: Path, tmp_path: Path) -> None:
    paths = app_paths(tmp_path / "portable")
    game = _game_from_rom(rom_directory / "forge-test.nes", paths.database)
    (paths.cores / "nestopia_libretro.dll").touch()
    command, result_path = GameLauncher(paths).prepare(game, fullscreen=True)
    config_path = Path(command[-1])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert command[1:3] == ["-m", "forge_emulation.runtime"]
    assert config["game_id"] == game.id
    assert config["fullscreen"] is True
    assert result_path.parent == config_path.parent
    assert Path(config["save_path"]).is_relative_to(paths.saves)
    assert config["controller_profiles"] == {}


def test_frozen_launcher_uses_internal_runtime(
    monkeypatch: pytest.MonkeyPatch, rom_directory: Path, tmp_path: Path
) -> None:
    paths = app_paths(tmp_path / "portable")
    game = _game_from_rom(rom_directory / "forge-test.nes", paths.database)
    (paths.cores / "nestopia_libretro.dll").touch()
    runtime = paths.root / "_internal" / "ForgeEmulationRuntime.exe"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.touch()
    monkeypatch.setattr("forge_emulation.launch.sys.frozen", True, raising=False)
    command, _ = GameLauncher(paths).prepare(game)
    assert command[0] == str(runtime)
    assert command[1] == "--config"


def test_launcher_requires_selected_core(rom_directory: Path, tmp_path: Path) -> None:
    paths = app_paths(tmp_path / "portable")
    game = _game_from_rom(rom_directory / "forge-test.sfc", paths.database)
    with pytest.raises(LaunchError, match="not installed"):
        GameLauncher(paths).prepare(game)


def test_launcher_reads_results_and_rejects_invalid_json(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    assert GameLauncher.read_result(result_path)["exit_reason"] == "runtime-terminated"
    result_path.write_text('{"exit_reason":"user-exit"}', encoding="utf-8")
    assert GameLauncher.read_result(result_path)["exit_reason"] == "user-exit"
    result_path.write_text("[]", encoding="utf-8")
    with pytest.raises(LaunchError, match="invalid"):
        GameLauncher.read_result(result_path)


def test_missing_linked_file_reports_clear_error(rom_directory: Path, tmp_path: Path) -> None:
    game = _game_from_rom(rom_directory / "forge-test.gb", tmp_path / "library.sqlite3")
    game.source_path.unlink()
    with pytest.raises(ContentError, match="unavailable"):
        materialize_game(game, tmp_path / "cache")


def test_bad_zip_is_reported(tmp_path: Path) -> None:
    archive_path = tmp_path / "broken.zip"
    archive_path.write_bytes(b"not a zip")
    from forge_emulation.scanner import ScanError

    with pytest.raises(ScanError, match="Could not inspect"):
        inspect_file(archive_path)


def test_archive_size_mismatch_is_rejected(rom_directory: Path, tmp_path: Path) -> None:
    archive_path = tmp_path / "game.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.write(rom_directory / "forge-test.nes", "forge-test.nes")
    game = _game_from_rom(archive_path, tmp_path / "library.sqlite3")
    from dataclasses import replace

    with pytest.raises(ContentError, match="size"):
        materialize_game(replace(game, size=game.size + 1), tmp_path / "cache")
