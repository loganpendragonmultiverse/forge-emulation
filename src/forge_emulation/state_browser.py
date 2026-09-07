from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

STATE_MAGIC = b"FORGESTATE1\n"


def state_metadata(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("State links are not supported.")
    with path.open("rb") as handle:
        if handle.read(len(STATE_MAGIC)) != STATE_MAGIC:
            raise ValueError("Invalid state header.")
        size_bytes = handle.read(4)
        if len(size_bytes) != 4:
            raise ValueError("Truncated state header.")
        size = struct.unpack("<I", size_bytes)[0]
        if size > 65536:
            raise ValueError("State metadata exceeds the limit.")
        data = handle.read(size)
        if len(data) != size:
            raise ValueError("Truncated state metadata.")
        value = json.loads(data)
        if not isinstance(value, dict) or any(
            not isinstance(value.get(key), str)
            for key in ["game_id", "core", "core_version", "created_at"]
        ):
            raise ValueError("Missing state metadata.")
        return {key: value[key] for key in ["game_id", "core", "core_version", "created_at"]}


def browse_states(directory: Path, game_id: str, core: str, version: str) -> list[dict[str, Any]]:
    rows = []
    for slot in range(1, 10):
        path = directory / f"slot-{slot}.state"
        if not path.exists():
            continue
        try:
            metadata = state_metadata(path)
            warnings = []
            if metadata["game_id"] != game_id:
                warnings.append("Different game")
            if metadata["core"] != core:
                warnings.append("Different core")
            if metadata["core_version"] != version:
                warnings.append("Different core version; loading is blocked")
            thumbnail = path.with_suffix(".png")
            rows.append(
                {
                    "slot": slot,
                    **metadata,
                    "warning": "; ".join(warnings),
                    "thumbnail": str(thumbnail)
                    if thumbnail.is_file()
                    and not thumbnail.is_symlink()
                    and thumbnail.stat().st_size < 2 * 1024 * 1024
                    else None,
                }
            )
        except (OSError, ValueError) as error:
            rows.append(
                {
                    "slot": slot,
                    "warning": str(error),
                    "thumbnail": None,
                    "created_at": "Unreadable",
                    "core_version": "unknown",
                }
            )
    return rows
