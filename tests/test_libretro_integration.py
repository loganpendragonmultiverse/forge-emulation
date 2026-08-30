from __future__ import annotations

from pathlib import Path

import pytest

from forge_emulation.libretro import LibretroCore

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("core_filename", "rom_filename", "expected_name"),
    [
        ("nestopia_libretro.dll", "forge-test.nes", "Nestopia"),
        ("bsnes_libretro.dll", "forge-test.sfc", "bsnes"),
        ("sameboy_libretro.dll", "forge-test.gb", "SameBoy"),
        ("sameboy_libretro.dll", "forge-test.gbc", "SameBoy"),
        ("blastem_libretro.dll", "forge-test.md", "BlastEm"),
        ("mgba_libretro.dll", "forge-test.gba", "mGBA"),
        ("smsplus_libretro.dll", "forge-test.gg", "SMS Plus GX"),
        ("stella2014_libretro.dll", "forge-test.a26", "Stella 2014"),
    ],
)
def test_core_loads_and_runs_original_test_cartridge(
    rom_directory: Path,
    tmp_path: Path,
    core_filename: str,
    rom_filename: str,
    expected_name: str,
) -> None:
    core_path = PROJECT_ROOT / "cores" / core_filename
    if not core_path.is_file():
        pytest.skip(f"Optional integration core is absent: {core_filename}")
    frames: list[tuple[int, int]] = []
    core = LibretroCore(core_path, tmp_path / "system", tmp_path / "saves")
    core.configure_callbacks(
        video=lambda _data, width, height, _pitch: frames.append((width, height)),
        audio_sample=lambda _left, _right: None,
        audio_batch=lambda _data, count: count,
        input_poll=lambda: None,
        input_state=lambda _port, _device, _index, _control: 0,
    )
    try:
        assert core.name == expected_name
        core.initialize()
        av_info = core.load_game(rom_directory / rom_filename)
        assert av_info.geometry.base_width > 0
        assert av_info.geometry.base_height > 0
        for _ in range(6):
            core.run()
        assert frames
        state = core.serialize()
        assert state
        core.unserialize(state)
    finally:
        core.close()
