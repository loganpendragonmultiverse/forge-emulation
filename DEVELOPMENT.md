# Development contract

ForgeEmulation 1.2 is a finite Windows release, not an emulator framework. Changes must preserve the local-first linked-library model, isolated runtime process, fixed core manifest, and absence of telemetry or ROM acquisition.

Every change requires focused tests and must keep Ruff, strict MyPy, pytest, core integration, and packaging checks green. A change to a core binary requires a new binary hash, verified source commit, corresponding source archive, license review, and all-system runtime verification.

Public releases are human-approved. The repository does not auto-publish binaries, create tags, or update core pins.

Version 1.2 keeps profiles in
`userdata/controller-profiles.json`, preferences in `userdata/preferences.json`, and
local artwork under `userdata/artwork`. Future releases that alter controller or runtime
behavior require hardware acceptance for gameplay remapping, controller library/quick-menu
navigation, affected settings paths, and real user-owned cartridges.
