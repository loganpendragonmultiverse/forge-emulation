"""Bounded playback history and compatible, checksummed session snapshots."""

from __future__ import annotations

import hashlib
import json
import struct
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAGIC = b"FORGESTATE1\n"
MAX_STATE_BYTES = 64 * 1024 * 1024


def encode_state(metadata: dict[str, str], state: bytes) -> bytes:
    if not state or len(state) > MAX_STATE_BYTES:
        raise ValueError("State size is outside the supported 64 MiB limit.")
    header = json.dumps(
        {**metadata, "sha256": hashlib.sha256(state).hexdigest()}, sort_keys=True
    ).encode()
    return MAGIC + struct.pack("<I", len(header)) + header + state


def decode_state(data: bytes, *, game_id: str, core: str, version: str) -> bytes:
    start = len(MAGIC) + 4
    if len(data) < start or not data.startswith(MAGIC):
        raise ValueError("Invalid or truncated ForgeEmulation state.")
    size = struct.unpack("<I", data[len(MAGIC) : start])[0]
    if size > 65536 or len(data) < start + size:
        raise ValueError("Invalid or truncated state metadata.")
    metadata = json.loads(data[start : start + size])
    if not isinstance(metadata, dict):
        raise ValueError("Invalid state metadata.")
    if (metadata.get("game_id"), metadata.get("core"), metadata.get("core_version")) != (
        game_id,
        core,
        version,
    ):
        raise ValueError("State game/core/version differs; the state was not loaded.")
    state = data[start + size :]
    if not state or len(state) > MAX_STATE_BYTES:
        raise ValueError("Invalid state size.")
    if "sha256" in metadata and metadata["sha256"] != hashlib.sha256(state).hexdigest():
        raise ValueError("State checksum failed; the state was not loaded.")
    return state


def read_state(path: Path, *, game_id: str, core: str, version: str) -> bytes:
    if path.is_symlink() or path.stat().st_size > MAX_STATE_BYTES + 65536 + 32:
        raise ValueError("State file is linked or exceeds the size limit.")
    return decode_state(path.read_bytes(), game_id=game_id, core=core, version=version)


def write_state(path: Path, metadata: dict[str, str], state: bytes) -> None:
    data = encode_state(metadata, state)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("State links are not supported.")
    temporary = path.with_suffix(path.suffix + ".partial")
    if temporary.is_symlink():
        raise ValueError("State staging links are not supported.")
    temporary.write_bytes(data)
    temporary.replace(path)


@dataclass(frozen=True)
class RewindPoint:
    state: bytes
    frame: bytes | None
    width: int
    height: int
    pitch: int

    @property
    def size(self) -> int:
        return len(self.state) + len(self.frame or b"")


class RewindBuffer:
    def __init__(self, max_points: int, max_bytes: int = 64 * 1024 * 1024):
        self.max_points = max(0, max_points)
        self.max_bytes = max(0, max_bytes)
        self.points: deque[RewindPoint] = deque()
        self.bytes_used = 0

    def push(self, point: RewindPoint) -> bool:
        if not self.max_points or point.size > self.max_bytes:
            return False
        while self.points and (
            len(self.points) >= self.max_points or self.bytes_used + point.size > self.max_bytes
        ):
            self.bytes_used -= self.points.popleft().size
        self.points.append(point)
        self.bytes_used += point.size
        return True

    def pop(self) -> RewindPoint | None:
        if not self.points:
            return None
        point = self.points.pop()
        self.bytes_used -= point.size
        return point

    def clear(self) -> None:
        self.points.clear()
        self.bytes_used = 0


class SessionStates:
    """Keep suspend state separate from manual slots, and one undo-load snapshot."""

    def __init__(self, directory: Path, game_id: str, core: Any):
        self.directory, self.game_id, self.core = directory, game_id, core
        self.undo: bytes | None = None

    def load(self, path: Path) -> None:
        state = read_state(
            path, game_id=self.game_id, core=self.core.name, version=self.core.version
        )
        before = self.core.serialize()
        try:
            self.core.unserialize(state)
        except Exception:
            self.core.unserialize(before)
            raise
        self.undo = before

    def undo_load(self) -> None:
        if self.undo is None:
            raise ValueError("There is no state load to undo in this session.")
        state = self.undo
        before = self.core.serialize()
        self.core.unserialize(state)
        self.undo = before

    def save(self, path: Path, timestamp: str) -> None:
        write_state(
            path,
            {
                "game_id": self.game_id,
                "core": self.core.name,
                "core_version": self.core.version,
                "created_at": timestamp,
            },
            self.core.serialize(),
        )
