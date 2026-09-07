# Development contract

ForgeEmulation 1.2 is a finite Windows release, not an emulator framework. Changes must preserve the local-first linked-library model, isolated runtime process, fixed core manifest, and absence of telemetry or ROM acquisition.

Every change requires focused tests and must keep Ruff, strict MyPy, pytest, core integration, and packaging checks green. A change to a core binary requires a new binary hash, verified source commit, corresponding source archive, license review, and all-system runtime verification.

Public releases are human-approved. The repository does not auto-publish binaries, create tags, or update core pins.

Version 1.2 keeps profiles in
`userdata/controller-profiles.json`, preferences in `userdata/preferences.json`, and
local artwork under `userdata/artwork`. Future releases that alter controller or runtime
behavior require hardware acceptance for gameplay remapping, controller library/quick-menu
navigation, affected settings paths, and real user-owned cartridges.

## Version 1.3.0: reviewed improvements

Add a save-state browser with thumbnails and compatibility warnings, plus guided controller mapping, live input feedback and validated profile exchange.

Browse nine save slots with capture timestamps, core versions and available thumbnails; select the next launch slot without changing game files. State loading rejects a different core version. Controller mapping walks through gameplay and library controls, waits for held controls to be released, and shows live inputs. Versioned profile import validates actions, binding types and limits before previewing replacement counts; export refuses existing files. Core binaries and pins remain unchanged. Automated tests use generated fixtures; physical-controller and user-owned-cartridge acceptance is required before the stable Windows release.

Candidate validation: 53 automated tests passed at 92.03% coverage; packaged frontend and all nine generated-ROM runtime targets passed; ZIP layout and SHA-256 verified. Physical-controller and user-owned-game acceptance is pending.
