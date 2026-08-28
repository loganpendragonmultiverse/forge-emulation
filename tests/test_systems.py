from __future__ import annotations

from pathlib import Path

import pytest

from forge_emulation.systems import SYSTEMS, detect_system


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("forge-test.nes", "nes"),
        ("forge-test.sfc", "snes"),
        ("forge-test.gb", "gb"),
        ("forge-test.gbc", "gbc"),
        ("forge-test.md", "genesis"),
    ],
)
def test_detects_generated_cartridges(rom_directory: Path, filename: str, expected: str) -> None:
    content = (rom_directory / filename).read_bytes()
    assert detect_system(filename, content, len(content)) == (expected, "header")


def test_ambiguous_bin_is_rejected() -> None:
    assert detect_system("unknown.bin", bytes(4096), 4096) is None


def test_every_system_exposes_user_facing_core_information() -> None:
    for system in SYSTEMS:
        assert system.core_name
        assert system.core_version
        assert system.core_license
        assert system.core_filename.endswith("_libretro.dll")
