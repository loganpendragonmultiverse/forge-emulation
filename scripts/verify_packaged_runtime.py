from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))

from generate_test_roms import write_test_roms  # noqa: E402

PROJECT_ROOT = SCRIPT_ROOT.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_files(package: Path, manifest: dict[str, Any]) -> None:
    visible_entries = {path.name for path in package.iterdir()}
    expected_entries = {
        "_internal",
        "ForgeEmulation.exe",
        "LICENSE.txt",
        "Open-Source-Notices",
        "README.txt",
    }
    if visible_entries != expected_entries:
        raise RuntimeError(
            f"Unexpected top-level package layout: {sorted(visible_entries ^ expected_entries)}"
        )
    notices = package / "Open-Source-Notices"
    required = [
        package / "ForgeEmulation.exe",
        package / "_internal" / "ForgeEmulationRuntime.exe",
        package / "LICENSE.txt",
        package / "README.txt",
        notices / "THIRD_PARTY_LICENSES.md",
        notices / "CORE_LICENSE_MATRIX.md",
        notices / "core-manifest.json",
    ]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"Packaged file is missing: {path.name}")
    for core in manifest["cores"]:
        binary = package / "_internal" / "cores" / core["binary"]
        source = notices / "corresponding-source" / core["source_archive"]
        license_path = notices / "licenses" / core["license_file"]
        if sha256(binary) != core["binary_sha256"]:
            raise RuntimeError(f"Packaged core hash mismatch: {binary.name}")
        if sha256(source) != core["source_archive_sha256"]:
            raise RuntimeError(f"Packaged source hash mismatch: {source.name}")
        if not license_path.is_file():
            raise RuntimeError(f"Packaged license is missing: {license_path.name}")
    if list(package.rglob("icuuc.dll")):
        raise RuntimeError("A non-system ICU DLL contaminated the packaged Qt runtime.")
    if list(package.rglob("*Handoff*")):
        raise RuntimeError("A handoff document leaked into the user package.")


def verify_runtime(package: Path, manifest: dict[str, Any]) -> None:
    systems = [
        ("nes", "nestopia_libretro.dll", "forge-test.nes"),
        ("snes", "bsnes_libretro.dll", "forge-test.sfc"),
        ("gb", "sameboy_libretro.dll", "forge-test.gb"),
        ("gbc", "sameboy_libretro.dll", "forge-test.gbc"),
        ("genesis", "blastem_libretro.dll", "forge-test.md"),
    ]
    with tempfile.TemporaryDirectory(prefix="forge-emulation-package-") as temporary:
        root = Path(temporary)
        roms = root / "roms"
        write_test_roms(roms)
        environment = os.environ.copy()
        environment.update({"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"})
        for system_id, core_filename, rom_filename in systems:
            session = root / system_id
            session.mkdir(parents=True)
            result_path = session / "result.json"
            config = {
                "core_path": str(package / "_internal" / "cores" / core_filename),
                "content_path": str(roms / rom_filename),
                "save_path": str(session / "save.srm"),
                "state_path": str(session / "slot-0.state"),
                "screenshot_dir": str(session / "screenshots"),
                "system_dir": str(session / "system"),
                "log_path": str(session / "runtime.log"),
                "result_path": str(result_path),
                "game_id": f"package-test:{system_id}",
                "title": rom_filename,
                "audio": system_id == "nes",
                "max_frames": 4,
            }
            config_path = session / "launch.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            completed = subprocess.run(
                [
                    str(package / "_internal" / "ForgeEmulationRuntime.exe"),
                    "--config",
                    str(config_path),
                ],
                check=False,
                env=environment,
                timeout=45,
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if completed.returncode or result.get("exit_reason") != "normal":
                raise RuntimeError(f"Packaged {system_id} runtime failed: {result}")

        frontend_environment = os.environ.copy()
        startup_probe = root / "frontend-startup.ready"
        frontend_environment.update(
            {
                "QT_QPA_PLATFORM": "offscreen",
                "FORGE_EMULATION_ROOT": str(root / "frontend"),
                "FORGE_EMULATION_STARTUP_PROBE": str(startup_probe),
            }
        )
        process = subprocess.Popen([str(package / "ForgeEmulation.exe")], env=frontend_environment)
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline and not startup_probe.is_file():
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Packaged frontend exited during startup with {process.returncode}"
                    )
                time.sleep(0.1)
            if not startup_probe.is_file():
                raise RuntimeError("Packaged frontend never confirmed that its window was created.")
            if startup_probe.read_text(encoding="utf-8") != "ForgeEmulation-ready\n":
                raise RuntimeError("Packaged frontend returned an invalid startup marker.")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a packaged ForgeEmulation release.")
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    package = args.package.resolve()
    manifest = json.loads((PROJECT_ROOT / "third_party" / "core-manifest.json").read_text())
    verify_files(package, manifest)
    verify_runtime(package, manifest)
    print("Packaged frontend and all five runtime targets passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
