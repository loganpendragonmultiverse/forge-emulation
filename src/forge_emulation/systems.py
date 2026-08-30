from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .models import SystemDefinition

NINTENDO_LOGO = bytes.fromhex(
    "CEED6666CC0D000B03730083000C000D0008111F8889000EDCCCC6E6DDDDD999"
    "BBBB67636E0EECCCDDDC999FBBB9333E"
)

SYSTEMS: tuple[SystemDefinition, ...] = (
    SystemDefinition(
        id="nes",
        name="Nintendo Entertainment System",
        short_name="NES",
        extensions=frozenset({".nes", ".unf", ".unif"}),
        core_filename="nestopia_libretro.dll",
        core_name="Nestopia",
        core_version="1.54.0 (bd355ea)",
        core_license="GPL-2.0",
        accent="#e35d6a",
    ),
    SystemDefinition(
        id="snes",
        name="Super Nintendo Entertainment System",
        short_name="SNES",
        extensions=frozenset({".sfc", ".smc"}),
        core_filename="bsnes_libretro.dll",
        core_name="bsnes",
        core_version="115",
        core_license="GPL-3.0-or-later",
        accent="#8d7be8",
    ),
    SystemDefinition(
        id="gb",
        name="Nintendo Game Boy",
        short_name="GB",
        extensions=frozenset({".gb"}),
        core_filename="sameboy_libretro.dll",
        core_name="SameBoy",
        core_version="1.0.3 (8230189)",
        core_license="MIT",
        accent="#8ca35c",
    ),
    SystemDefinition(
        id="gbc",
        name="Nintendo Game Boy Color",
        short_name="GBC",
        extensions=frozenset({".gbc"}),
        core_filename="sameboy_libretro.dll",
        core_name="SameBoy",
        core_version="1.0.3 (8230189)",
        core_license="MIT",
        accent="#4bb7a7",
    ),
    SystemDefinition(
        id="genesis",
        name="Sega Genesis / Mega Drive",
        short_name="GEN",
        extensions=frozenset({".md", ".gen", ".bin"}),
        core_filename="blastem_libretro.dll",
        core_name="BlastEm",
        core_version="0.6.3-pre",
        core_license="GPL-3.0",
        accent="#4b80e6",
    ),
    SystemDefinition(
        id="gba",
        name="Nintendo Game Boy Advance",
        short_name="GBA",
        extensions=frozenset({".gba"}),
        core_filename="mgba_libretro.dll",
        core_name="mGBA",
        core_version="0.11-219 (e31759b)",
        core_license="MPL-2.0",
        accent="#6d63d9",
    ),
    SystemDefinition(
        id="sms",
        name="Sega Master System",
        short_name="SMS",
        extensions=frozenset({".sms"}),
        core_filename="smsplus_libretro.dll",
        core_name="SMS Plus GX",
        core_version="1.8 (8a63f82)",
        core_license="GPL-2.0",
        accent="#d34343",
    ),
    SystemDefinition(
        id="gamegear",
        name="Sega Game Gear",
        short_name="GG",
        extensions=frozenset({".gg"}),
        core_filename="smsplus_libretro.dll",
        core_name="SMS Plus GX",
        core_version="1.8 (8a63f82)",
        core_license="GPL-2.0",
        accent="#3e9e8d",
    ),
    SystemDefinition(
        id="atari2600",
        name="Atari 2600",
        short_name="A2600",
        extensions=frozenset({".a26"}),
        core_filename="stella2014_libretro.dll",
        core_name="Stella 2014",
        core_version="3.9.3 (4a7da82)",
        core_license="GPL-2.0",
        accent="#c46f31",
    ),
)

SYSTEM_BY_ID = {system.id: system for system in SYSTEMS}
SUPPORTED_EXTENSIONS = frozenset(extension for system in SYSTEMS for extension in system.extensions)


def _looks_like_game_boy(header: bytes) -> bool:
    return len(header) >= 0x150 and header[0x104:0x134] == NINTENDO_LOGO


def _looks_like_snes(header: bytes, file_size: int) -> bool:
    offset = 512 if file_size % 0x8000 == 512 else 0
    for base in (0x7FC0, 0xFFC0, 0x40FFC0):
        location = offset + base
        if location + 0x20 > len(header):
            continue
        title = header[location : location + 21]
        map_mode = header[location + 0x15]
        checksum = int.from_bytes(header[location + 0x1E : location + 0x20], "little")
        complement = int.from_bytes(header[location + 0x1C : location + 0x1E], "little")
        printable = sum(32 <= byte <= 126 for byte in title) >= 15
        checksum_valid = (checksum ^ complement) == 0xFFFF and checksum != 0
        if printable and map_mode & 0x0F in {0, 1, 2, 3, 5, 10} and checksum_valid:
            return True
    return False


def detect_system(filename: str, header: bytes, file_size: int) -> tuple[str, str] | None:
    extension = Path(filename).suffix.lower()
    if header.startswith(b"NES\x1a") or header.startswith(b"UNIF"):
        return "nes", "header"
    if _looks_like_game_boy(header):
        color_flag = header[0x143]
        return ("gbc" if color_flag in {0x80, 0xC0} or extension == ".gbc" else "gb", "header")
    if len(header) >= 0x104 and header[0x100:0x104] == b"SEGA":
        return "genesis", "header"
    if extension in {".sms", ".gg"} and any(
        offset + 8 <= len(header) and header[offset : offset + 8] == b"TMR SEGA"
        for offset in (0x1FF0, 0x3FF0, 0x7FF0)
    ):
        return ("gamegear" if extension == ".gg" else "sms"), "header"
    if extension in {".sfc", ".smc"} and _looks_like_snes(header, file_size):
        return "snes", "header"

    if extension == ".bin":
        return None
    for system in SYSTEMS:
        if extension in system.extensions:
            return system.id, "extension-fallback"
    return None


def accepted_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS or path.suffix.lower() == ".zip"


def system_names(ids: Iterable[str]) -> list[str]:
    return [SYSTEM_BY_ID[system_id].short_name for system_id in ids if system_id in SYSTEM_BY_ID]
