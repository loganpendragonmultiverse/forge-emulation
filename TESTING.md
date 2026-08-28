# Testing

Run the complete release gate from the project root:

```powershell
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
```

The suite generates original, minimal cartridge images for every supported system. These fixtures contain no commercial code or artwork. Integration tests load the pinned DLLs, run frames, and round-trip save states. Full runtime tests also exercise SDL rendering for NES, SNES, Game Boy, Game Boy Color, and Genesis.

Coverage is enforced at 85% for the backend and libretro boundary. Qt layout code and the interactive pygame loop are excluded from line coverage and instead receive application startup, rendered-window, and packaged-runtime smoke checks during release verification.

Manual acceptance for a release:

1. Import raw files and a ZIP from a path containing spaces.
2. Verify all five system filters and favorites.
3. Launch one legal cartridge for each system with audio and a controller.
4. Save and load a state, create a screenshot, reset, toggle fullscreen, and exit.
5. Confirm playtime increments and a core failure leaves the frontend open.
6. Run the portable package from a clean Windows user profile.

The packaged verifier requires an explicit marker written only after the Qt window is created. A living PyInstaller crash dialog is not accepted as successful startup. The archive verifier also rejects nested wrapper folders, top-level runtime helpers, handoff files, and non-system `icuuc.dll` contamination.
