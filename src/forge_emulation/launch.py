from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .content import materialize_game
from .models import Game
from .paths import AppPaths
from .systems import SYSTEM_BY_ID


class LaunchError(RuntimeError):
    pass


class GameLauncher:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def prepare(self, game: Game, *, fullscreen: bool = False) -> tuple[list[str], Path]:
        system = SYSTEM_BY_ID[game.system_id]
        core_path = self.paths.cores / system.core_filename
        if not core_path.is_file():
            raise LaunchError(
                f"The {system.short_name} core is not installed: {system.core_filename}"
            )
        content_path = materialize_game(game, self.paths.cache / "content")
        safe_game_id = game.sha256[:24]
        session_key = uuid.uuid4().hex
        session_dir = self.paths.cache / "sessions" / session_key
        session_dir.mkdir(parents=True, exist_ok=False)
        config_path = session_dir / "launch.json"
        result_path = session_dir / "result.json"
        config = {
            "game_id": game.id,
            "title": game.title,
            "system_id": game.system_id,
            "content_path": str(content_path),
            "core_path": str(core_path),
            "save_path": str(self.paths.saves / game.system_id / safe_game_id / "save.srm"),
            "state_path": str(self.paths.states / game.system_id / safe_game_id / "slot-0.state"),
            "screenshot_dir": str(self.paths.screenshots / game.system_id / safe_game_id),
            "system_dir": str(self.paths.userdata / "system"),
            "log_path": str(self.paths.logs / "runtime.log"),
            "result_path": str(result_path),
            "fullscreen": fullscreen,
            "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        if getattr(sys, "frozen", False):
            runtime_executable = self.paths.root / "_internal" / "ForgeEmulationRuntime.exe"
            if not runtime_executable.is_file():
                raise LaunchError("The internal emulator runtime is missing from the installation.")
            command = [str(runtime_executable), "--config", str(config_path)]
        else:
            command = [
                sys.executable,
                "-m",
                "forge_emulation.runtime",
                "--config",
                str(config_path),
            ]
        return command, result_path

    @staticmethod
    def start(command: list[str]) -> subprocess.Popen[bytes]:
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        return subprocess.Popen(command, creationflags=creation_flags)

    @staticmethod
    def read_result(result_path: Path) -> dict[str, object]:
        if not result_path.is_file():
            return {"exit_reason": "runtime-terminated", "error": "Runtime returned no result."}
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LaunchError("The runtime result could not be read.") from exc
        if not isinstance(result, dict):
            raise LaunchError("The runtime returned an invalid result.")
        return result
