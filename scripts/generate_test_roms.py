from __future__ import annotations

import argparse
from pathlib import Path

NINTENDO_LOGO = bytes.fromhex(
    "CEED6666CC0D000B03730083000C000D0008111F8889000EDCCCC6E6DDDDD999"
    "BBBB67636E0EECCCDDDC999FBBB9333E"
)


def nes_rom() -> bytes:
    header = bytearray(b"NES\x1a")
    header.extend((1, 1, 0, 0))
    header.extend(bytes(8))
    program = bytearray([0xEA] * 0x4000)
    program[0:4] = bytes((0x78, 0xD8, 0x4C, 0x00))
    program[4] = 0x80
    for vector in (0x3FFA, 0x3FFC, 0x3FFE):
        program[vector : vector + 2] = bytes((0x00, 0x80))
    return bytes(header + program + bytearray(0x2000))


def game_boy_rom(*, color: bool) -> bytes:
    rom = bytearray(0x8000)
    rom[0x100:0x104] = bytes((0x00, 0xC3, 0x50, 0x01))
    rom[0x104:0x134] = NINTENDO_LOGO
    rom[0x134:0x143] = b"FORGE TEST ROM "
    rom[0x143] = 0x80 if color else 0
    rom[0x144:0x146] = b"00"
    rom[0x146] = 0
    rom[0x147] = 0
    rom[0x148] = 0
    rom[0x149] = 0
    rom[0x14A] = 1
    rom[0x14B] = 0x33
    rom[0x14C] = 0
    checksum = 0
    for value in rom[0x134:0x14D]:
        checksum = (checksum - value - 1) & 0xFF
    rom[0x14D] = checksum
    rom[0x150:0x152] = bytes((0x18, 0xFE))
    global_checksum = sum(rom[:0x14E]) + sum(rom[0x150:])
    rom[0x14E:0x150] = (global_checksum & 0xFFFF).to_bytes(2, "big")
    return bytes(rom)


def genesis_rom() -> bytes:
    rom = bytearray(0x40000)
    rom[0:4] = (0x00FF0000).to_bytes(4, "big")
    rom[4:8] = (0x00000200).to_bytes(4, "big")
    for offset in range(8, 0x100, 4):
        rom[offset : offset + 4] = (0x00000200).to_bytes(4, "big")
    rom[0x100:0x110] = b"SEGA MEGA DRIVE "
    rom[0x110:0x120] = b"(C)FORGE 2026   "
    rom[0x120:0x150] = b"FORGEEMULATION TEST CARTRIDGE".ljust(48, b" ")
    rom[0x150:0x180] = b"FORGEEMULATION TEST CARTRIDGE".ljust(48, b" ")
    rom[0x180:0x18E] = b"GM 00000000-00"
    rom[0x190:0x1A0] = b"J6              "
    rom[0x1A0:0x1A4] = (0).to_bytes(4, "big")
    rom[0x1A4:0x1A8] = (len(rom) - 1).to_bytes(4, "big")
    rom[0x1A8:0x1B0] = bytes(8)
    rom[0x1F0:0x200] = b"JUE".ljust(16, b" ")
    rom[0x200:0x202] = bytes((0x60, 0xFE))
    checksum = sum(
        int.from_bytes(rom[offset : offset + 2], "big") for offset in range(0x200, len(rom), 2)
    )
    rom[0x18E:0x190] = (checksum & 0xFFFF).to_bytes(2, "big")
    return bytes(rom)


def snes_rom() -> bytes:
    rom = bytearray(0x8000)
    rom[0:6] = bytes((0x78, 0xD8, 0x18, 0xFB, 0x80, 0xFE))
    header = 0x7FC0
    rom[header : header + 21] = b"FORGEEMULATION TEST  ".ljust(21, b" ")
    rom[header + 0x15] = 0x20
    rom[header + 0x16] = 0x00
    rom[header + 0x17] = 0x05
    rom[header + 0x18] = 0x00
    rom[header + 0x19] = 0x01
    rom[header + 0x1A] = 0x33
    rom[header + 0x1B] = 0x00
    rom[header + 0x1C : header + 0x1E] = (0xEDCB).to_bytes(2, "little")
    rom[header + 0x1E : header + 0x20] = (0x1234).to_bytes(2, "little")
    rom[0x7FFA:0x8000] = (0x8000).to_bytes(2, "little") * 3
    return bytes(rom)


def write_test_roms(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    images = {
        "forge-test.nes": nes_rom(),
        "forge-test.gb": game_boy_rom(color=False),
        "forge-test.gbc": game_boy_rom(color=True),
        "forge-test.md": genesis_rom(),
        "forge-test.sfc": snes_rom(),
    }
    for filename, content in images.items():
        (destination / filename).write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate original smoke-test cartridge images.")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    write_test_roms(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
