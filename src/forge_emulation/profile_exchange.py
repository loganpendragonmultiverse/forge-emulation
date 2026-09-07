from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .controller import DEFAULT_BINDINGS, ControllerProfileStore


def read_profiles(path: Path) -> dict[str, dict[str, Any]]:
    if path.stat().st_size > 65536:
        raise ValueError("Profile file exceeds 64 KB.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or not isinstance(data.get("profiles"), dict)
    ):
        raise ValueError("Expected a version 1 controller profile file.")
    result = {}
    for guid, profile in data["profiles"].items():
        if (
            not isinstance(guid, str)
            or not guid
            or not isinstance(profile, dict)
            or not isinstance(profile.get("controller_name"), str)
            or not isinstance(profile.get("bindings"), dict)
        ):
            raise ValueError("Invalid controller profile.")
        bindings = {}
        for action, binding in profile["bindings"].items():
            if action not in DEFAULT_BINDINGS or not isinstance(binding, dict):
                raise ValueError("Unknown action or binding.")
            kind = binding.get("kind")
            index = binding.get("index")
            if (
                kind not in {"button", "axis", "hat"}
                or type(index) is not int
                or not 0 <= index <= 127
            ):
                raise ValueError("Invalid control kind or index.")
            allowed = (
                {"kind", "index"}
                | ({"direction"} if kind in {"hat", "axis"} else set())
                | ({"axis"} if kind == "hat" else set())
            )
            if (
                set(binding) - allowed
                or kind in {"hat", "axis"}
                and (
                    type(binding.get("direction")) is not int or binding["direction"] not in {-1, 1}
                )
                or kind == "hat"
                and binding.get("axis") not in {"x", "y"}
            ):
                raise ValueError("Invalid direction or binding fields.")
            bindings[action] = dict(binding)
        result[guid] = {"controller_name": profile["controller_name"], "bindings": bindings}
    return result


def export_profiles(store: ControllerProfileStore, path: Path) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump({"version": 1, "profiles": store.export_profiles()}, handle, indent=2)
