from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

PROFILE_VERSION = 1

GAMEPLAY_ACTIONS: tuple[tuple[str, str, int], ...] = (
    ("b", "B", 0),
    ("y", "Y", 1),
    ("select", "Select", 2),
    ("start", "Start", 3),
    ("up", "D-pad up", 4),
    ("down", "D-pad down", 5),
    ("left", "D-pad left", 6),
    ("right", "D-pad right", 7),
    ("a", "A", 8),
    ("x", "X", 9),
    ("l", "L", 10),
    ("r", "R", 11),
)

LIBRARY_ACTIONS: tuple[tuple[str, str], ...] = (
    ("library_activate", "Library select"),
    ("library_back", "Library back"),
)

DEFAULT_BINDINGS: dict[str, dict[str, int | str]] = {
    "b": {"kind": "button", "index": 0},
    "a": {"kind": "button", "index": 1},
    "y": {"kind": "button", "index": 2},
    "x": {"kind": "button", "index": 3},
    "select": {"kind": "button", "index": 4},
    "start": {"kind": "button", "index": 6},
    "l": {"kind": "button", "index": 9},
    "r": {"kind": "button", "index": 10},
    "up": {"kind": "hat", "index": 0, "axis": "y", "direction": 1},
    "down": {"kind": "hat", "index": 0, "axis": "y", "direction": -1},
    "left": {"kind": "hat", "index": 0, "axis": "x", "direction": -1},
    "right": {"kind": "hat", "index": 0, "axis": "x", "direction": 1},
    "library_activate": {"kind": "button", "index": 0},
    "library_back": {"kind": "button", "index": 1},
}


class JoystickLike(Protocol):
    def get_numbuttons(self) -> int: ...

    def get_button(self, index: int) -> int: ...

    def get_numhats(self) -> int: ...

    def get_hat(self, index: int) -> tuple[float, float]: ...

    def get_numaxes(self) -> int: ...

    def get_axis(self, index: int) -> float: ...


def default_bindings() -> dict[str, dict[str, int | str]]:
    return deepcopy(DEFAULT_BINDINGS)


def binding_label(binding: dict[str, Any] | None) -> str:
    if not binding:
        return "Not assigned"
    kind = binding.get("kind")
    index = int(binding.get("index", 0))
    if kind == "button":
        return f"Button {index + 1}"
    if kind == "hat":
        axis = str(binding.get("axis", "x")).upper()
        direction = "+" if int(binding.get("direction", 1)) > 0 else "−"
        return f"D-pad {axis}{direction}"
    if kind == "axis":
        direction = "+" if int(binding.get("direction", 1)) > 0 else "−"
        return f"Axis {index + 1} {direction}"
    return "Not assigned"


def binding_pressed(joystick: JoystickLike, binding: dict[str, Any] | None) -> bool:
    if not binding:
        return False
    kind = binding.get("kind")
    index = int(binding.get("index", -1))
    if kind == "button" and 0 <= index < joystick.get_numbuttons():
        return bool(joystick.get_button(index))
    if kind == "hat" and 0 <= index < joystick.get_numhats():
        horizontal, vertical = joystick.get_hat(index)
        hat_value = horizontal if binding.get("axis") == "x" else vertical
        return hat_value == int(binding.get("direction", 0))
    if kind == "axis" and 0 <= index < joystick.get_numaxes():
        axis_value = joystick.get_axis(index)
        direction = int(binding.get("direction", 0))
        return axis_value >= 0.65 if direction > 0 else axis_value <= -0.65
    return False


def capture_inputs(joystick: JoystickLike) -> set[tuple[str, int, str, int]]:
    active: set[tuple[str, int, str, int]] = set()
    for index in range(joystick.get_numbuttons()):
        if joystick.get_button(index):
            active.add(("button", index, "", 1))
    for index in range(joystick.get_numhats()):
        horizontal_value, vertical_value = joystick.get_hat(index)
        horizontal, vertical = int(horizontal_value), int(vertical_value)
        if horizontal:
            active.add(("hat", index, "x", int(horizontal)))
        if vertical:
            active.add(("hat", index, "y", int(vertical)))
    for index in range(joystick.get_numaxes()):
        value = joystick.get_axis(index)
        if abs(value) >= 0.65:
            active.add(("axis", index, "", 1 if value > 0 else -1))
    return active


def captured_binding(value: tuple[str, int, str, int]) -> dict[str, int | str]:
    kind, index, axis, direction = value
    binding: dict[str, int | str] = {"kind": kind, "index": index}
    if axis:
        binding["axis"] = axis
    if kind in {"hat", "axis"}:
        binding["direction"] = direction
    return binding


@dataclass(slots=True)
class ControllerProfileStore:
    path: Path
    profiles: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path) -> ControllerProfileStore:
        profiles: dict[str, dict[str, Any]] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if (
                    isinstance(data, dict)
                    and data.get("version") == PROFILE_VERSION
                    and isinstance(data.get("profiles"), dict)
                ):
                    profiles = data["profiles"]
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                profiles = {}
        return cls(path=path, profiles=profiles)

    def bindings_for(self, guid: str) -> dict[str, dict[str, int | str]]:
        profile = self.profiles.get(guid, {})
        stored = profile.get("bindings", {}) if isinstance(profile, dict) else {}
        bindings = default_bindings()
        if isinstance(stored, dict):
            for action, binding in stored.items():
                if action in bindings and isinstance(binding, dict):
                    bindings[action] = dict(binding)
        return bindings

    def set_binding(
        self,
        guid: str,
        controller_name: str,
        action: str,
        binding: dict[str, int | str],
    ) -> None:
        if action not in DEFAULT_BINDINGS:
            raise ValueError(f"Unknown controller action: {action}")
        profile = self.profiles.setdefault(
            guid,
            {"controller_name": controller_name, "bindings": default_bindings()},
        )
        profile["controller_name"] = controller_name
        profile.setdefault("bindings", {})[action] = dict(binding)
        self.save()

    def reset(self, guid: str, controller_name: str) -> None:
        self.profiles[guid] = {
            "controller_name": controller_name,
            "bindings": default_bindings(),
        }
        self.save()

    def export_profiles(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self.profiles)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".partial")
        temporary.write_text(
            json.dumps(
                {"version": PROFILE_VERSION, "profiles": self.profiles},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)
