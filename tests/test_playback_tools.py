from __future__ import annotations

import json
import struct

import pygame
import pytest

from forge_emulation import runtime
from forge_emulation.playback import (
    MAGIC,
    RewindBuffer,
    RewindPoint,
    SessionStates,
    decode_state,
    encode_state,
    read_state,
    write_state,
)
from forge_emulation.settings import RuntimeSettings, SettingsStore


class FakeCore:
    name = "Fixture"
    version = "1"
    value = b"initial"

    def serialize(self):
        return self.value

    def unserialize(self, value):
        if value == b"rejected":
            raise RuntimeError("Core rejected this state")
        self.value = value

    def configure_callbacks(self, **kwargs):
        pass

    def run(self):
        self.value += b"x"


def metadata():
    return {"game_id": "fixture", "core": "Fixture", "core_version": "1", "created_at": "now"}


def test_checked_state_roundtrip_and_legacy_support(tmp_path):
    path = tmp_path / "slot-1.state"
    write_state(path, metadata(), b"state")
    assert read_state(path, game_id="fixture", core="Fixture", version="1") == b"state"
    old = json.dumps(metadata()).encode()
    legacy = MAGIC + struct.pack("<I", len(old)) + old + b"old"
    assert decode_state(legacy, game_id="fixture", core="Fixture", version="1") == b"old"


@pytest.mark.parametrize(
    "data", [b"", MAGIC, MAGIC + struct.pack("<I", 65537), MAGIC + struct.pack("<I", 99) + b"{}"]
)
def test_truncated_or_oversized_header_rejected(data):
    with pytest.raises(ValueError):
        decode_state(data, game_id="fixture", core="Fixture", version="1")


def test_checksum_and_identity_fail_before_core_changes(tmp_path):
    path = tmp_path / "state"
    data = encode_state(metadata(), b"payload")
    path.write_bytes(data[:-1] + b"X")
    core = FakeCore()
    states = SessionStates(tmp_path, "fixture", core)
    with pytest.raises(ValueError):
        states.load(path)
    assert core.value == b"initial" and states.undo is None
    path.write_bytes(data)
    with pytest.raises(ValueError):
        read_state(path, game_id="other", core="Fixture", version="1")
    with pytest.raises(ValueError):
        encode_state(metadata(), b"")


def test_rewind_budget_evicts_oldest_and_releases_memory():
    buffer = RewindBuffer(3, 9)
    for value in [b"aa", b"bb", b"cc", b"dd"]:
        assert buffer.push(RewindPoint(value, b"x", 1, 1, 1))
    assert buffer.bytes_used == 9 and len(buffer.points) == 3
    assert buffer.pop().state == b"dd"
    assert buffer.pop().state == b"cc"
    assert buffer.pop().state == b"bb"
    assert buffer.pop() is None and buffer.bytes_used == 0
    assert not buffer.push(RewindPoint(b"far too large", None, 0, 0, 0))
    assert not RewindBuffer(0).push(RewindPoint(b"x", None, 0, 0, 0))
    buffer.push(RewindPoint(b"x", None, 0, 0, 0))
    buffer.clear()
    assert not buffer.points and buffer.bytes_used == 0


def test_suspend_separate_slot_and_undo_load(tmp_path):
    core = FakeCore()
    states = SessionStates(tmp_path, "fixture", core)
    slot = tmp_path / "slot-1.state"
    states.save(slot, "now")
    core.value = b"suspended"
    states.save(tmp_path / "suspend.state", "later")
    core.value = b"playing"
    states.load(tmp_path / "suspend.state")
    assert core.value == b"suspended"
    states.undo_load()
    assert core.value == b"playing"
    states.undo_load()
    assert core.value == b"suspended"
    states.load(slot)
    assert core.value == b"initial"
    with pytest.raises(ValueError):
        SessionStates(tmp_path, "fixture", core).undo_load()


def test_rejected_state_restores_original_core(tmp_path):
    path = tmp_path / "slot.state"
    write_state(path, metadata(), b"rejected")
    core = FakeCore()
    states = SessionStates(tmp_path, "fixture", core)
    with pytest.raises(RuntimeError):
        states.load(path)
    assert core.value == b"initial" and states.undo is None


def test_runtime_rewind_frame_restores_video_and_state(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "LibretroCore", lambda *args: FakeCore())
    session = runtime.RuntimeSession(
        {
            "core_path": "fixture",
            "content_path": "fixture",
            "save_path": str(tmp_path / "save"),
            "state_dir": str(tmp_path / "states"),
            "screenshot_dir": str(tmp_path / "screens"),
            "system_dir": str(tmp_path),
            "game_id": "fixture",
            "title": "Fixture",
            "rewind_seconds": 10,
        }
    )
    for _ in range(6):
        session._run_frame()
    assert len(session.rewind.points) == 1
    captured = session.core.value
    session.core.value = b"later"
    assert session._rewind_frame() and session.core.value == captured
    assert not session._rewind_frame()
    session._suspend()
    session.core.value = b"after suspend"
    session._resume()
    assert session.core.value == captured
    session._undo_load()
    assert session.core.value == b"after suspend"


def test_runtime_focus_pause_and_step_events(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "LibretroCore", lambda *args: FakeCore())
    session = runtime.RuntimeSession(
        {
            "core_path": "fixture",
            "content_path": "fixture",
            "save_path": str(tmp_path / "save"),
            "screenshot_dir": str(tmp_path),
            "system_dir": str(tmp_path),
            "game_id": "fixture",
            "title": "Fixture",
        }
    )
    monkeypatch.setattr(
        pygame.event,
        "get",
        lambda: [
            pygame.event.Event(pygame.WINDOWFOCUSLOST),
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PERIOD, mod=0),
        ],
    )
    session._handle_events(None)
    assert session.paused and session.step_pending


def test_playback_preferences_roundtrip_and_normalize(tmp_path):
    store = SettingsStore(tmp_path / "preferences.json")
    store.set_global(
        RuntimeSettings(
            rewind_seconds=30, fast_forward_speed=4, suspend_on_exit=True, resume_on_launch=True
        )
    )
    loaded = SettingsStore(store.path).for_game("fixture")
    assert loaded.rewind_seconds == 30 and loaded.suspend_on_exit
    assert loaded.fast_forward_speed == 4 and loaded.resume_on_launch
    assert (
        RuntimeSettings(rewind_seconds=9, fast_forward_speed=100).normalized().rewind_seconds == 0
    )
    assert RuntimeSettings(fast_forward_speed=100).normalized().fast_forward_speed == 2
