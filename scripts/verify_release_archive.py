from __future__ import annotations

import argparse
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

EXPECTED_ROOTS = {
    "_internal",
    "ForgeEmulation.exe",
    "LICENSE.txt",
    "Open-Source-Notices",
    "README.txt",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the public Windows archive layout.")
    parser.add_argument("archive")
    args = parser.parse_args()
    try:
        with ZipFile(args.archive) as archive:
            names = [PurePosixPath(name.replace("\\", "/")) for name in archive.namelist()]
    except (BadZipFile, OSError) as exc:
        raise RuntimeError(f"Could not inspect release archive: {args.archive}") from exc
    if not names:
        raise RuntimeError("Release archive is empty.")
    if any(path.is_absolute() or ".." in path.parts for path in names):
        raise RuntimeError("Release archive contains an unsafe path.")
    roots = {path.parts[0] for path in names if path.parts}
    if roots != EXPECTED_ROOTS:
        raise RuntimeError(f"Release archive has an unexpected root layout: {sorted(roots)}")
    files = {path.as_posix().rstrip("/") for path in names}
    if "ForgeEmulation.exe" not in files:
        raise RuntimeError("The user-facing ForgeEmulation launcher is missing.")
    if "_internal/ForgeEmulationRuntime.exe" not in files:
        raise RuntimeError("The internal emulator runtime is missing.")
    top_level_executables = {
        path.name for path in names if len(path.parts) == 1 and path.suffix.lower() == ".exe"
    }
    if top_level_executables != {"ForgeEmulation.exe"}:
        raise RuntimeError("The archive must expose exactly one user-facing executable.")
    lowered = [path.as_posix().lower() for path in names]
    if any("handoff" in path for path in lowered):
        raise RuntimeError("A handoff document leaked into the release archive.")
    if any(path.endswith("/icuuc.dll") or path == "icuuc.dll" for path in lowered):
        raise RuntimeError("A non-system ICU DLL contaminated the release archive.")
    print("Flat archive layout, single launcher, and dependency boundaries verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
