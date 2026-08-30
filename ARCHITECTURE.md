# Architecture

ForgeEmulation has two processes with a deliberately narrow boundary.

The Qt frontend owns scanning, the SQLite library, filtering, favorites, launch configuration, and playtime records. It never loads emulator code. `GameLauncher` writes a per-session JSON file and starts `ForgeEmulationRuntime.exe`.

The pygame runtime loads one pinned libretro DLL, materializes video and audio callbacks,
reads one controller, and owns save RAM, nine save-state slots, screenshots, the quick
menu, scaling/filtering, volume, pause, reset, and fullscreen. It writes a small result
JSON on exit. A core crash therefore terminates the game process rather than the library.

Portable global preferences and per-game overrides live in
`userdata/preferences.json`. User-supplied artwork is copied into `userdata/artwork`;
ROMs remain linked in place. Backups use an allowlisted, checksummed ZIP manifest and
never include ROM files, caches, logs, or previous backups. Diagnostics omit ROM paths,
titles, usernames, and save data.

User data is portable and remains beside the application under `userdata/`. The SQLite database stores hashes and linked paths, not ROM bytes. Extracted ZIP content is stored in `userdata/cache/content/<sha256>/` and can be regenerated from the linked archive.

Core selection is fixed in `systems.py`; 1.0 has no downloadable-core manager or arbitrary plugin loading. `third_party/core-manifest.json` is the authority for bundled binaries and corresponding source.
