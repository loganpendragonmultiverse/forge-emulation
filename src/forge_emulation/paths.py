from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    userdata: Path
    cores: Path
    database: Path
    logs: Path
    saves: Path
    states: Path
    screenshots: Path
    cache: Path

    def ensure(self) -> None:
        for path in (
            self.userdata,
            self.cores,
            self.logs,
            self.saves,
            self.states,
            self.screenshots,
            self.cache,
        ):
            path.mkdir(parents=True, exist_ok=True)


def application_root() -> Path:
    override = os.environ.get("FORGE_EMULATION_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def app_paths(root: Path | None = None) -> AppPaths:
    base = (root or application_root()).resolve()
    userdata = base / "userdata"
    cores = base / "_internal" / "cores" if getattr(sys, "frozen", False) else base / "cores"
    paths = AppPaths(
        root=base,
        userdata=userdata,
        cores=cores,
        database=userdata / "library.sqlite3",
        logs=userdata / "logs",
        saves=userdata / "saves",
        states=userdata / "states",
        screenshots=userdata / "screenshots",
        cache=userdata / "cache",
    )
    paths.ensure()
    return paths
