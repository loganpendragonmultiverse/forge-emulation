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
