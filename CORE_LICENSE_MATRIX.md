# Emulator core license and source matrix

ForgeEmulation 1.0 bundles four replaceable libretro core DLLs. The frontend does not
modify these cores. Every distributed binary must retain its upstream license and be
accompanied by the complete source used to build that binary.

| Core | Systems | Runtime version | License | Binary SHA-256 | Source commit | Correspondence evidence |
|---|---|---|---|---|---|---|
| Nestopia | NES | 1.54.0 bd355ea | GPL-2.0 | `27dbe95806e58d751ea87e14580a78201fa084ac5f9f5998aede1389cd516ac3` | `bd355eafcc7b90487eaae3a9d39c17dac6468280` | Runtime version embeds the source commit. |
| bsnes | SNES | 115 6d19eef5 | GPL-3.0-or-later | `4e0242c71b9151bf06acad9cf7e0f1e1181d80bf4b24f1cda515eaeec97f2cd7` | `6d19eef5835a792e241e33194b4c1e9b75405b88` | Compiled from this exact checkout in recorded GitHub Actions run 33189661783; runtime version embeds the short commit. |
| SameBoy | Game Boy / Color | 1.0.3 8230189 | MIT | `b171875daa8b3303d65b18d717bad30e65b104da996b1d309d71a35459ce791f` | `8230189896a8bb6598574d302ba0ad3658f98ab4` | Runtime version embeds the source commit. |
| BlastEm | Genesis / Mega Drive | 0.6.3-pre | GPL-3.0 | `f75d7e522454b4aa5cf35ce493a748ae9a66e3db1c1ceb735d044b6922f01ab0` | `aeb16cd0750fc23ab5e804efeb96f9b207985c41` | Compiled from this exact checkout in recorded GitHub Actions run 33189661783. |

The machine-readable authority is `third_party/core-manifest.json`. Source snapshots
and full license texts are included in each Windows release under
`Open-Source-Notices/`. A binary or source pin may change only after its hash,
corresponding source, license compatibility, and all-system runtime checks pass.
The reproducible build record is included under `third_party/build-provenance/`.
