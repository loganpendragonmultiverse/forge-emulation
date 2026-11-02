# Development contract

ForgeEmulation 1.6.0 is a finite Windows release, not an emulator framework. Changes must preserve the local-first linked-library model, isolated runtime process, fixed core manifest, and absence of telemetry or ROM acquisition.

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


## 1.4.0 location review

Preview only: do not update roms.available, last_seen, history or saves. A complete readable selected-folder scan is required before absence becomes a missing candidate; offline/incomplete roots remain unverified. Content and ZIP members are not read. Require independent review, Windows CI and packaged UI acceptance before publication.

Independent technical review found no actionable findings. Preserve the tagged Windows build gates for startup, generated-cartridge runtimes and archive layout; report interactive packaged location-review and physical-device acceptance as unverified until exercised.

## 1.5.0 organization release

Add organization tables without rewriting games, ROMs or sessions. Keep all writes in explicit
user actions and SQLite transactions. Organization exchange cannot create games or alter
ROM locations, saves, favorites, core pins or play history. Preserve bounded validation and
recovery export before import. The new UI receives offscreen Qt acceptance and rendered
inspection; existing Windows integration and tagged packaging gates remain required.

Design references: RetroArch playlist documentation and ES-DE USERGUIDE custom collections.
This release adapts library concepts without copying their implementation or claiming parity.

## 1.6.0 play sessions and workbench

The maintainer explicitly authorized a second same-day release for hands-on testing after
publication. This is an exception to the earlier pre-release hardware acceptance timing;
physical controller, real cartridge and interactive packaged acceptance remain unverified and
must be reported as such. Keep all CI, coverage, core/source/license and package gates.

Use bounded rewind memory, separate manual/suspend files and version-bound snapshots. Validate
snapshots before loading and keep an undo state for the active runtime. Bulk metadata changes
and content-verified relinking use transactions; stale or incomplete plans cannot partially
apply. Recovery removal prevalidates the companion and rolls back interrupted moves.
Saved views are local preferences, and CSV notes require explicit selection.

References: RetroArch rewind/fast-forward and save-state documentation, mGBA feature overview,
and ES-DE custom collection guidance. These inform useful workflows, not a parity claim.
