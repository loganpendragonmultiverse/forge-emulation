# Changelog

## 1.6.0 - 2026-10-16

- Add bounded opt-in rewind, 2×/4× silent fast-forward, paused frame stepping and focus-loss pause.
- Add separate suspend/resume snapshots, snapshot checksums and one-step undo for successful loads.
- Add a table workbench with transactional bulk organization, private-notes opt-in CSV export and reusable saved views.
- Paginate the card grid while keeping complete filtered views available to the workbench and export.
- Add a state/screenshot manager with preview, checked exports and recoverable removal of states and thumbnails.
- Add background content-verified moved-file relinking with revision checks, all-or-nothing apply and preserved history and saves.
- Extend generated-cartridge Windows and packaged runtime checks to suspend/resume across all nine targets. Core pins and licenses are unchanged.


## 1.5.0 — 2026-10-16

- Add named collections with rename/removal and multi-collection membership without copying games.
- Add local play status, five-star ratings, notes and normalized tags, with status/rating badges on cards.
- Combine collection, status, exact-tag, minimum-rating and never-launched filters with five stable sort orders.
- Add read-only global and per-game session history with timestamps, duration, core and exit reason.
- Add bounded JSON organization export/import matched to existing game content, with preview counts,
  validation before writes, transactional replacement and a recovery export before UI imports.
- Keep organization in the existing SQLite backup; preserve ROM locations, favorites, history,
  title/artwork overrides, saves and core pins. Make game details scroll at smaller window sizes.
- Physical-controller and user-owned-game acceptance remain unverified. Runtime behavior and cores
  are unchanged; automated Qt acceptance covers the new organization flow.

## 1.4.0 - 2026-10-15

- Add a selected-folder, read-only preview of stored ROM locations with missing candidates and unavailable/incomplete-folder safeguards.
- Preserve all availability flags, metadata, play history, saves and core pins; ZIP member contents remain unverified.

## 1.2.0 - 2026-08-29

- Added an in-game quick menu and nine independent save-state slots.
- Added global and per-game scaling, video filter, fullscreen, volume, mute, and
  default-slot preferences.
- Added checksummed local backup/restore, Continue Playing, privacy-safe diagnostics,
  custom local titles, and user-supplied artwork.
- Added Game Boy Advance through mGBA, Master System and Game Gear through SMS Plus GX,
  and Atari 2600 through Stella 2014 with pinned source and license provenance.
- Added persistent per-controller profiles with remapping for every supported gameplay action.
- Added controller-driven spatial navigation, selection, and back behavior throughout the library.
- Corrected dialog backgrounds, combo boxes, spin boxes, focus states, and message-box
  buttons for consistent dark-theme contrast on Windows.

## 1.0.0 - 2026-08-28

- Added a portable Windows library for NES, SNES, Game Boy, Game Boy Color, and Sega Genesis / Mega Drive.
- Added pinned Nestopia, bsnes, SameBoy, and BlastEm runtimes with source and license provenance.
- Added linked folder scanning, ZIP inspection, search, favorites, playtime, controller input, save RAM, save states, screenshots, pause, reset, and fullscreen.
- Added an isolated emulator process, local SQLite storage, synthetic cartridge integration tests, and reproducible release packaging.
- Corrected the pre-release Windows bundle to exclude an incompatible build-machine ICU DLL, expose one launcher, and extract without an extra wrapper directory.
- Added per-system emulator core, version, license, and readiness information.
- Added an in-app Controls & help page covering the library, mouse, keyboard, controllers, and bundled cores.

## Version 1.3.0: reviewed improvements

Add a save-state browser with thumbnails and compatibility warnings, plus guided controller mapping, live input feedback and validated profile exchange.

Browse nine save slots with capture timestamps, core versions and available thumbnails; select the next launch slot without changing game files. State loading rejects a different core version. Controller mapping walks through gameplay and library controls, waits for held controls to be released, and shows live inputs. Versioned profile import validates actions, binding types and limits before previewing replacement counts; export refuses existing files. Core binaries and pins remain unchanged. Automated tests use generated fixtures; physical-controller and user-owned-cartridge acceptance is required before the stable Windows release.

Backup export now uses SQLite backup snapshots and stages other files before hashing and archiving, preventing checksum drift during WAL checkpoints. The controller capture test also verifies held/released input and cancellation when switching mappings.
