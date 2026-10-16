from __future__ import annotations

from pathlib import Path

import pytest

from forge_emulation.runtime import RuntimeSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("core_filename", "rom_filename"),
    [
        ("nestopia_libretro.dll", "forge-test.nes"),
        ("bsnes_libretro.dll", "forge-test.sfc"),
        ("sameboy_libretro.dll", "forge-test.gb"),
        ("sameboy_libretro.dll", "forge-test.gbc"),
        ("blastem_libretro.dll", "forge-test.md"),
        ("mgba_libretro.dll", "forge-test.gba"),
        ("stella2014_libretro.dll", "forge-test.a26"),
    ],
)
def test_full_runtime_renders_frames_with_each_supported_system(
    monkeypatch: pytest.MonkeyPatch,
    rom_directory: Path,
    tmp_path: Path,
    core_filename: str,
    rom_filename: str,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    core_path = PROJECT_ROOT / "cores" / core_filename
    if not core_path.is_file():
        pytest.skip(f"Optional integration core is absent: {core_filename}")
    session = RuntimeSession(
        {
            "core_path": str(core_path),
            "content_path": str(rom_directory / rom_filename),
            "save_path": str(tmp_path / "saves" / "save.srm"),
            "state_path": str(tmp_path / "states" / "slot-0.state"),
            "screenshot_dir": str(tmp_path / "screenshots"),
            "system_dir": str(tmp_path / "system"),
            "game_id": f"test:{rom_filename}",
            "title": rom_filename,
            "audio": False,
            "max_frames": 4,
        }
    )
    result = session.run()
    assert result["exit_reason"] == "normal"
    assert result["core_name"]
    assert session.frame_width > 0
    assert session.frame_height > 0


@pytest.mark.parametrize(
    ("core_filename", "rom_filename"),
    [
        ("nestopia_libretro.dll", "forge-test.nes"),
        ("bsnes_libretro.dll", "forge-test.sfc"),
        ("sameboy_libretro.dll", "forge-test.gb"),
        ("sameboy_libretro.dll", "forge-test.gbc"),
        ("blastem_libretro.dll", "forge-test.md"),
        ("mgba_libretro.dll", "forge-test.gba"),
        ("smsplus_libretro.dll", "forge-test.sms"),
        ("smsplus_libretro.dll", "forge-test.gg"),
        ("stella2014_libretro.dll", "forge-test.a26"),
    ],
)
def test_suspend_resume_and_rewind_with_pinned_cores(
    monkeypatch, rom_directory, tmp_path, core_filename, rom_filename
):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    core_path = PROJECT_ROOT / "cores" / core_filename
    if not core_path.is_file():
        pytest.skip("Pinned Windows core is not present in this environment")
    config = {
        "core_path": str(core_path),
        "content_path": str(rom_directory / rom_filename),
        "save_path": str(tmp_path / "save.srm"),
        "state_dir": str(tmp_path / "states"),
        "screenshot_dir": str(tmp_path / "screenshots"),
        "system_dir": str(tmp_path / "system"),
        "game_id": "fixture:" + rom_filename,
        "title": rom_filename,
        "audio": False,
        "max_frames": 18,
        "rewind_seconds": 10,
        "suspend_on_exit": True,
        "resume_on_launch": True,
    }
    first = RuntimeSession(config)
    assert first.run()["exit_reason"] == "normal"
    assert len(first.rewind.points) >= 2
    suspend = tmp_path / "states" / "suspend.state"
    assert suspend.is_file()
    assert not (suspend.parent / "slot-1.state").exists()
    second = RuntimeSession(config)
    assert second.run()["exit_reason"] == "normal"
    assert second.session_states.undo is not None
