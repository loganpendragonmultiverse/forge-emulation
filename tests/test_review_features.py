from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from forge_emulation.controller import ControllerProfileStore, default_bindings
from forge_emulation.profile_exchange import export_profiles, read_profiles
from forge_emulation.state_browser import STATE_MAGIC, browse_states, state_metadata


def state(path: Path, version: str = "1") -> None:
    header = json.dumps(
        {
            "game_id": "game",
            "core": "Core",
            "core_version": version,
            "created_at": "2026-09-07T00:00:00Z",
        }
    ).encode()
    path.write_bytes(STATE_MAGIC + struct.pack("<I", len(header)) + header + b"payload")


def test_state_browser_is_read_only_and_warns_on_version(tmp_path: Path) -> None:
    file = tmp_path / "slot-1.state"
    state(file)
    before = file.read_bytes()
    (tmp_path / "slot-1.png").write_bytes(b"fixture")
    rows = browse_states(tmp_path, "game", "Core", "2")
    assert rows[0]["thumbnail"]
    assert "version" in rows[0]["warning"]
    assert file.read_bytes() == before
    assert not browse_states(tmp_path, "game", "Core", "1")[0]["warning"]
    assert "Different game" in browse_states(tmp_path, "other", "Other", "1")[0]["warning"]
    assert state_metadata(file)["core_version"] == "1"
    file.write_bytes(b"invalid")
    assert browse_states(tmp_path, "game", "Core", "1")[0]["created_at"] == "Unreadable"
    for data in [
        STATE_MAGIC,
        STATE_MAGIC + struct.pack("<I", 70000),
        STATE_MAGIC + struct.pack("<I", 50) + b"{}",
        STATE_MAGIC + struct.pack("<I", 2) + b"{}",
    ]:
        file.write_bytes(data)
        with pytest.raises(ValueError):
            state_metadata(file)


def test_profile_export_import_and_invalid_bindings(tmp_path: Path) -> None:
    store = ControllerProfileStore.load(tmp_path / "local.json")
    store.reset("guid", "Controller")
    output = tmp_path / "export.json"
    export_profiles(store, output)
    assert read_profiles(output) == store.export_profiles()
    with pytest.raises(FileExistsError):
        export_profiles(store, output)
    for binding in [
        {"kind": "button", "index": True},
        {"kind": "button", "index": -1},
        {"kind": "axis", "index": 0, "direction": 0},
        {"kind": "hat", "index": 0, "axis": "z", "direction": 1},
        {"kind": "button", "index": 1, "secret": "value"},
    ]:
        payload = {
            "version": 1,
            "profiles": {"g": {"controller_name": "Test", "bindings": {"a": binding}}},
        }
        output.write_text(json.dumps(payload))
        with pytest.raises(ValueError):
            read_profiles(output)
    output.write_text("{}")
    with pytest.raises(ValueError):
        read_profiles(output)
    output.write_text("x" * 65537)
    with pytest.raises(ValueError):
        read_profiles(output)
    assert default_bindings()["a"]["kind"] == "button"


def test_runtime_thumbnail_and_version_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pygame

    from forge_emulation.runtime import RuntimeSession

    class Core:
        name = "Core"
        version = "1"

        def serialize(self) -> bytes:
            return b"state"

        def unserialize(self, data: bytes) -> None:
            assert data == b"state"

    session = RuntimeSession.__new__(RuntimeSession)
    session.state_dir = tmp_path
    session.state_slot = 1
    session.game_id = "game"
    monkeypatch.setattr(session, "core", Core(), raising=False)
    surface = pygame.Surface((320, 240))
    surface.fill((20, 40, 60))
    monkeypatch.setattr(session, "_surface_from_frame", lambda: surface)
    session._save_state()
    assert (tmp_path / "slot-1.png").is_file()
    assert pygame.image.load(str(tmp_path / "slot-1.png")).get_size() == (240, 180)
    session._load_state()
    session.core.version = "2"
    with pytest.raises(RuntimeError, match="version differs"):
        session._load_state()
