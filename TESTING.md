# Testing

Run the complete release gate from the project root:

```powershell
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
```

The suite generates original, minimal cartridge images for every supported system. These
fixtures contain no commercial code or artwork. Integration tests load the pinned DLLs,
run frames, and round-trip save states. The packaged-runtime gate starts each of the nine
system targets in a fresh process, including both SMS Plus GX targets.

Coverage is enforced at 85% for the backend and libretro boundary. Qt layout code and the interactive pygame loop are excluded from line coverage and instead receive application startup, rendered-window, and packaged-runtime smoke checks during release verification.

Render the main library and shared dialog surfaces for visual inspection:

```powershell
.\.venv\Scripts\python.exe scripts\render_ui_smoke.py artifacts\ui-smoke.png
.\.venv\Scripts\python.exe scripts\render_dialog_smoke.py artifacts\dialog-smoke
```

Manual acceptance for a release:

1. Import raw files and a ZIP from a path containing spaces.
2. Verify all nine system filters, Favorites, and Continue Playing.
3. Launch one legal cartridge for each system with audio and a controller.
4. Open the quick menu with Escape/Tab and controller Select+Start.
5. Save and load two state slots, create a screenshot, reset, toggle fullscreen, and exit.
6. Verify all scaling/filtering choices plus volume and mute.
7. Export and restore a backup; confirm no ROM files were copied.
8. Edit a local title/artwork and verify search and card display.
9. Copy/save diagnostics and confirm private ROM paths and titles are absent.
10. Confirm playtime increments and a core failure leaves the frontend open.
11. Run the portable package from a clean Windows user profile.
12. Open Controller settings, remap a face button and a D-pad direction, relaunch a game, and
   confirm the saved profile is used without changing keyboard input.
13. With the frontend visible, navigate the sidebar, search, checkboxes, game cards, details, and
   documentation using the D-pad and left stick; select with the configured library select button
   and return from a filter or search with the configured library back button.

The packaged verifier requires an explicit marker written only after the Qt window is created. A living PyInstaller crash dialog is not accepted as successful startup. The archive verifier also rejects nested wrapper folders, top-level runtime helpers, handoff files, and non-system `icuuc.dll` contamination.

## Version 1.3.0: reviewed improvements

Add a save-state browser with thumbnails and compatibility warnings, plus guided controller mapping, live input feedback and validated profile exchange.

Browse nine save slots with capture timestamps, core versions and available thumbnails; select the next launch slot without changing game files. State loading rejects a different core version. Controller mapping walks through gameplay and library controls, waits for held controls to be released, and shows live inputs. Versioned profile import validates actions, binding types and limits before previewing replacement counts; export refuses existing files. Core binaries and pins remain unchanged. Automated tests use generated fixtures; physical-controller and user-owned-cartridge acceptance is required before the stable Windows release.

Candidate validation: 53 automated tests passed at 92.03% coverage; packaged frontend and all nine generated-ROM runtime targets passed; ZIP layout and SHA-256 verified. Physical-controller and user-owned-game acceptance is pending.


## Location-review acceptance

Test existing/missing/outside paths, unavailable and interrupted folder scans, unreadable children, archive-member uncertainty, stable output and unchanged database/ROM data. Verify the review dialog and background scan in the Windows package. No hardware/runtime behavior changes are intended; existing runtime release gates remain required.

## 1.5.0 organization acceptance

The organization tests cover additive reopening, collection rename/conflict/removal, annotation
validation, combined filters, stable sorting, read-only bounded history, path-free exports,
content-match imports, unknown-game skipping and transactional rollback. Offscreen Qt acceptance
edits annotations, selects collection memberships, combines filters, clears them and opens history.

For hands-on acceptance: create two collections, add a game to both, enter notes/tags/rating,
combine filters, rename and remove a collection, export metadata, change a note, import and review
the match count, then use the recovery JSON to restore the prior note. Confirm favorites, ROM
locations, saves and sessions survive. Physical controllers and user-owned cartridges cannot be
certified by generated fixtures or offscreen tests and remain unverified until exercised.

Windows PR CI for the organization implementation passed 84 tests at 93.34% coverage,
Ruff formatting/lint, strict mypy, dependency audit and CodeQL on October 16. The tagged
Windows packaging gate remains authoritative for the shipped binaries.

## 1.6.0 acceptance

Backend tests cover bounded rewind eviction, snapshot identity/checksum/size validation,
legacy states, load rollback and undo, settings persistence, bulk transactions, saved views,
CSV privacy/formula neutralization, media recovery rollback, and revision/content-checked
relinking. Offscreen Qt tests exercise the workbench, views, pagination and media manager.
Pinned-core Windows tests and the packaged-runtime gate exercise separate suspend/resume
for all nine generated-cartridge targets. Preserve the 85% coverage gate.

Manual testing later: hold rewind after playing; compare 2×/4× fast-forward, step a paused
frame, switch focus, save/resume suspend and undo a load; try a real controller and legal
cartridges. Review large-library pagination, bulk edits and saved filters, media export and
recovery, and moved raw/ZIP games. Synthetic automated sessions do not establish real-game
compatibility, physical controller acceptance, timing/audio quality or interactive package QA.
