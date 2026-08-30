from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SystemDefinition:
    id: str
    name: str
    short_name: str
    extensions: frozenset[str]
    core_filename: str
    core_name: str
    core_version: str
    core_license: str
    accent: str


@dataclass(frozen=True, slots=True)
class GameCandidate:
    game_id: str
    title: str
    system_id: str
    source_path: Path
    archive_member: str | None
    size: int
    sha256: str
    sha1: str
    crc32: str
    extension: str
    detection: str


@dataclass(frozen=True, slots=True)
class Game:
    id: str
    title: str
    custom_title: str | None
    artwork_path: Path | None
    system_id: str
    source_path: Path
    archive_member: str | None
    size: int
    sha256: str
    sha1: str
    crc32: str
    extension: str
    detection: str
    favorite: bool
    playtime_seconds: int
    session_count: int
    last_played: str | None
    added_at: str

    @property
    def display_title(self) -> str:
        return self.custom_title or self.title
