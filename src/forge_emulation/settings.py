from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    fullscreen: bool = False
    scaling: str = "fit"
    video_filter: str = "nearest"
    volume: int = 100
    muted: bool = False
    state_slot: int = 1

    def normalized(self) -> RuntimeSettings:
        return RuntimeSettings(
            fullscreen=bool(self.fullscreen),
            scaling=self.scaling if self.scaling in {"fit", "integer", "stretch"} else "fit",
            video_filter=(
                self.video_filter if self.video_filter in {"nearest", "smooth"} else "nearest"
            ),
            volume=max(0, min(100, int(self.volume))),
            muted=bool(self.muted),
            state_slot=max(1, min(9, int(self.state_slot))),
        )


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self.global_settings = RuntimeSettings()
        self.game_overrides: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        global_values = payload.get("global", {})
        if isinstance(global_values, dict):
            self.global_settings = self._from_values(global_values)
        overrides = payload.get("games", {})
        if isinstance(overrides, dict):
            allowed = {field.name for field in fields(RuntimeSettings)}
            self.game_overrides = {
                str(game_id): {key: value for key, value in values.items() if key in allowed}
                for game_id, values in overrides.items()
                if isinstance(values, dict)
            }

    @staticmethod
    def _from_values(values: dict[str, Any]) -> RuntimeSettings:
        allowed = {field.name for field in fields(RuntimeSettings)}
        return RuntimeSettings(
            **{key: value for key, value in values.items() if key in allowed}
        ).normalized()

    def for_game(self, game_id: str) -> RuntimeSettings:
        values = asdict(self.global_settings)
        values.update(self.game_overrides.get(game_id, {}))
        return self._from_values(values)

    def set_global(self, settings: RuntimeSettings) -> None:
        self.global_settings = settings.normalized()
        self.save()

    def set_game_override(self, game_id: str, values: dict[str, Any] | None) -> None:
        if values:
            self.game_overrides[game_id] = values
        else:
            self.game_overrides.pop(game_id, None)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": 1,
            "global": asdict(self.global_settings),
            "games": self.game_overrides,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".partial")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
