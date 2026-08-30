from __future__ import annotations

from pathlib import Path

import pytest

from forge_emulation.systems import SYSTEMS, detect_system


@pytest.mark.parametrize(
    ("filename", "expected", "method"),
    [
        ("forge-test.nes", "nes", "header"),
        ("forge-test.sfc", "snes", "header"),
        ("forge-test.gb", "gb", "header"),
        ("forge-test.gbc", "gbc", "header"),
        ("forge-test.md", "genesis", "header"),
        ("forge-test.gba", "gba", "extension-fallback"),
        ("forge-test.sms", "sms", "header"),
        ("forge-test.gg", "gamegear", "header"),
        ("forge-test.a26", "atari2600", "extension-fallback"),
    ],
)
def test_detects_generated_cartridges(
    rom_directory: Path, filename: str, expected: str, method: str
) -> None:
    content = (rom_directory / filename).read_bytes()
    assert detect_system(filename, content, len(content)) == (expected, method)


def test_ambiguous_bin_is_rejected() -> None:
    assert detect_system("unknown.bin", bytes(4096), 4096) is None


def test_every_system_exposes_user_facing_core_information() -> None:
    for system in SYSTEMS:
        assert system.core_name
        assert system.core_version
        assert system.core_license
        assert system.core_filename.endswith("_libretro.dll")
