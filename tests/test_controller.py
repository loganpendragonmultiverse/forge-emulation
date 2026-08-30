from __future__ import annotations

import json
from pathlib import Path

from forge_emulation.controller import (
    ControllerProfileStore,
    binding_label,
    binding_pressed,
    capture_inputs,
    captured_binding,
    default_bindings,
)


class FakeJoystick:
    def __init__(self) -> None:
        self.buttons = [0, 1, 0]
        self.hats = [(1, -1)]
        self.axes = [0.0, -0.8]

    def get_numbuttons(self) -> int:
        return len(self.buttons)

    def get_button(self, index: int) -> int:
        return self.buttons[index]

    def get_numhats(self) -> int:
        return len(self.hats)

    def get_hat(self, index: int) -> tuple[int, int]:
        return self.hats[index]

    def get_numaxes(self) -> int:
        return len(self.axes)

    def get_axis(self, index: int) -> float:
        return self.axes[index]


def test_bindings_read_buttons_hats_and_axes() -> None:
    joystick = FakeJoystick()
    assert binding_pressed(joystick, {"kind": "button", "index": 1})
    assert binding_pressed(joystick, {"kind": "hat", "index": 0, "axis": "x", "direction": 1})
    assert binding_pressed(joystick, {"kind": "axis", "index": 1, "direction": -1})
    assert not binding_pressed(joystick, {"kind": "button", "index": 20})


def test_capture_inputs_round_trips_to_bindings() -> None:
    active = capture_inputs(FakeJoystick())
    assert ("button", 1, "", 1) in active
    assert ("hat", 0, "x", 1) in active
    assert ("hat", 0, "y", -1) in active
    assert ("axis", 1, "", -1) in active
    assert binding_label(captured_binding(("axis", 1, "", -1))) == "Axis 2 −"


def test_profile_store_persists_per_controller_and_recovers_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "controller-profiles.json"
    store = ControllerProfileStore.load(path)
    store.set_binding("guid-1", "Test pad", "a", {"kind": "button", "index": 7})
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["profiles"]["guid-1"]["controller_name"] == "Test pad"
    assert ControllerProfileStore.load(path).bindings_for("guid-1")["a"]["index"] == 7
    assert ControllerProfileStore.load(path).bindings_for("other") == default_bindings()
    store.reset("guid-1", "Test pad")
    assert store.bindings_for("guid-1") == default_bindings()

    path.write_text("not json", encoding="utf-8")
    assert ControllerProfileStore.load(path).profiles == {}
    path.write_text("[]", encoding="utf-8")
    assert ControllerProfileStore.load(path).profiles == {}
