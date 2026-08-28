from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from pathlib import Path
from typing import Any
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "third_party" / "core-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path, expected: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    actual = sha256(temporary)
    if actual != expected:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Hash mismatch for {target.name}: expected {expected}, got {actual}")
    temporary.replace(target)


def main() -> int:
    manifest: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for core in manifest["cores"]:
        archive = ROOT / "third_party" / "binaries" / core["binary_archive"]
        if not archive.is_file():
            raise RuntimeError(f"Pinned binary archive is missing: {archive}")
        if sha256(archive) != core["binary_archive_sha256"]:
            raise RuntimeError(f"Pinned binary archive hash mismatch: {archive.name}")
        with ZipFile(archive) as bundle:
            member = next(name for name in bundle.namelist() if name.endswith(core["binary"]))
            target = ROOT / "cores" / core["binary"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
        if sha256(target) != core["binary_sha256"]:
            raise RuntimeError(f"Extracted core hash mismatch: {target.name}")
        source_url = f"{core['source_repository']}/archive/{core['source_commit']}.zip"
        source_target = ROOT / "third_party" / "source" / core["source_archive"]
        if not source_target.is_file() or sha256(source_target) != core["source_archive_sha256"]:
            print(f"Downloading {core['name']} corresponding source")
            download(source_url, source_target, core["source_archive_sha256"])
    print("All pinned cores and corresponding source archives verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
