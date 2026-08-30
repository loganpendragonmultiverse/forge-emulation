# Third-party components

The expansion candidate distributes seven libretro core binaries. Each portable package
also contains the recorded corresponding-source archive and upstream license notice.
SHA-256 hashes and source commits are machine-readable in `third_party/core-manifest.json`.

See [CORE_LICENSE_MATRIX.md](CORE_LICENSE_MATRIX.md) for the binary hashes and the
current source-correspondence evidence required before public release.

| Core | Systems | Version | License | Source |
|---|---|---:|---|---|
| Nestopia | NES | 1.54.0 bd355ea | GPL-2.0 | `libretro/nestopia` at `bd355eafcc7b90487eaae3a9d39c17dac6468280` |
| bsnes | SNES | 115 6d19eef5 | GPL-3.0-or-later | `libretro/bsnes-libretro` at `6d19eef5835a792e241e33194b4c1e9b75405b88` |
| SameBoy | Game Boy / Color | 1.0.3 8230189 | MIT | `libretro/SameBoy` at `8230189896a8bb6598574d302ba0ad3658f98ab4` |
| BlastEm | Genesis / Mega Drive | 0.6.3-pre | GPL-3.0 | `libretro/blastem` at `aeb16cd0750fc23ab5e804efeb96f9b207985c41` |
| mGBA | Game Boy Advance | 0.11-219 e31759b | MPL-2.0 | `mgba-emu/mgba` at `e31759b24e7a4e3899285ff720d7b573ac328ae7` |
| SMS Plus GX | Master System / Game Gear | 1.8 8a63f82 | GPL-2.0 | `libretro/smsplus-gx` at `8a63f82d3c3bbf7215a31f86a4aaa13fb68a579f` |
| Stella 2014 | Atari 2600 | 3.9.3 4a7da82 | GPL-2.0 | `libretro/stella2014-libretro` at `4a7da82595d27b8df7af1ecb467a64b642a41bc9` |

Runtime dependencies include Python 3.12.13, PySide6/Qt for Python 6.11.2, pygame-ce 2.5.8, and SDL 2.32.10. The portable package includes their primary license texts under `Open-Source-Notices/licenses/`. PySide6 and Qt are used under their open-source LGPL/GPL terms; pygame-ce is LGPL-2.1 and Python and SDL use their respective permissive licenses. No project name or trademark implies endorsement of ForgeEmulation.

The Nestopia and SameBoy buildbot archives were captured on 2026-08-27. The mGBA,
SMS Plus GX, and Stella 2014 archives were captured on 2026-08-29. Each exposes its
source commit in its runtime version string. ForgeEmulation's bsnes and
BlastEm binaries were compiled from the exact listed commits in GitHub Actions run
33189661783. Hashes, workflow evidence, and compiler details are retained under
`third_party/build-provenance/`.
