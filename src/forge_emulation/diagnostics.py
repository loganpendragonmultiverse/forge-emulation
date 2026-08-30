from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import pygame

from .database import LibraryDatabase
from .paths import AppPaths
from .systems import SYSTEMS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_diagnostics(paths: AppPaths, database: LibraryDatabase) -> dict[str, object]:
    controllers: list[str] = []
    try:
        pygame.joystick.init()
        controllers = [
            pygame.joystick.Joystick(index).get_name()
            for index in range(pygame.joystick.get_count())
        ]
    except pygame.error:
        controllers = []
    cores = []
    for system in SYSTEMS:
        path = paths.cores / system.core_filename
        cores.append(
            {
                "system": system.short_name,
                "core": system.core_name,
                "version": system.core_version,
                "installed": path.is_file(),
                "sha256": _sha256(path) if path.is_file() else None,
            }
        )
    try:
        writable = os.access(paths.userdata, os.W_OK)
    except OSError:
        writable = False
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "app": "ForgeEmulation local test candidate",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "userdata_writable": writable,
        "database_integrity": database.integrity_check(),
        "library_games": len(database.list_games()),
        "controllers": controllers,
        "cores": cores,
    }


def diagnostic_text(paths: AppPaths, database: LibraryDatabase) -> str:
    return json.dumps(build_diagnostics(paths, database), indent=2, sort_keys=True)
