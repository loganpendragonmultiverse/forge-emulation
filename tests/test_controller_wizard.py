import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from forge_emulation.controller import ControllerProfileStore
from forge_emulation.ui import main_window as ui


class Pad:
    def get_guid(self) -> str:
        return "fixture-guid"

    def get_name(self) -> str:
        return "Fixture controller"


def test_guided_capture_requires_release_and_manual_capture_cancels_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.pygame.joystick, "get_count", lambda: 1)
    monkeypatch.setattr(ui.pygame.joystick, "Joystick", lambda _index: Pad())
    active = {("button", 0, "", 1)}
    monkeypatch.setattr(ui, "capture_inputs", lambda _joystick: set(active))
    store = ControllerProfileStore.load(tmp_path / "profiles.json")
    dialog = ui.ControllerSettingsDialog(store)
    dialog.timer.stop()
    dialog._start_wizard()
    first = dialog.waiting_action
    assert first is not None
    remaining = len(dialog.wizard_actions)
    dialog._poll_capture()
    assert dialog.waiting_action == first
    active.clear()
    dialog._poll_capture()
    active.add(("button", 0, "", 1))
    dialog._poll_capture()
    assert store.bindings_for("fixture-guid")[first] == {"kind": "button", "index": 0}
    assert len(dialog.wizard_actions) == remaining - 1
    dialog._manual_capture("a")
    assert not dialog.wizard_actions
    assert dialog.waiting_action == "a"
    dialog._start_wizard()
    dialog._controller_changed(0)
    assert not dialog.wizard_actions
    assert dialog.waiting_action is None
    dialog.close()
    app.processEvents()
