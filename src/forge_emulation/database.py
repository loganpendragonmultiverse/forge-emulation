from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .models import Game, GameCandidate

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    system_id TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    sha1 TEXT NOT NULL,
    crc32 TEXT NOT NULL,
    extension TEXT NOT NULL,
    detection TEXT NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0,
    playtime_seconds INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    last_played TEXT,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roms (
    path TEXT NOT NULL,
    archive_member TEXT NOT NULL DEFAULT '',
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    available INTEGER NOT NULL DEFAULT 1,
    last_seen TEXT NOT NULL,
    PRIMARY KEY(path, archive_member)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    core_filename TEXT NOT NULL,
    core_version TEXT,
    exit_reason TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_system ON games(system_id);
CREATE INDEX IF NOT EXISTS idx_games_last_played ON games(last_played);
CREATE INDEX IF NOT EXISTS idx_roms_game ON roms(game_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class LibraryDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def import_candidates(self, candidates: Iterable[GameCandidate]) -> tuple[int, int]:
        imported = 0
        locations = 0
        now = _now()
        with self.connect() as connection:
            for game in candidates:
                existing = connection.execute(
                    "SELECT 1 FROM games WHERE id = ?", (game.game_id,)
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO games (
                        id, title, system_id, size, sha256, sha1, crc32, extension,
                        detection, added_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        system_id = excluded.system_id,
                        size = excluded.size,
                        sha256 = excluded.sha256,
                        sha1 = excluded.sha1,
                        crc32 = excluded.crc32,
                        extension = excluded.extension,
                        detection = excluded.detection
                    """,
                    (
                        game.game_id,
                        game.title,
                        game.system_id,
                        game.size,
                        game.sha256,
                        game.sha1,
                        game.crc32,
                        game.extension,
                        game.detection,
                        now,
                    ),
                )
                cursor = connection.execute(
                    """
                    INSERT INTO roms(path, archive_member, game_id, available, last_seen)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(path, archive_member) DO UPDATE SET
                        game_id = excluded.game_id,
                        available = 1,
                        last_seen = excluded.last_seen
                    """,
                    (str(game.source_path), game.archive_member or "", game.game_id, now),
                )
                imported += int(existing is None)
                locations += int(cursor.rowcount > 0)
        return imported, locations

    def list_games(
        self,
        *,
        system_id: str | None = None,
        query: str = "",
        favorites_only: bool = False,
    ) -> list[Game]:
        conditions = ["r.available = 1"]
        parameters: list[object] = []
        if system_id:
            conditions.append("g.system_id = ?")
            parameters.append(system_id)
        if query:
            conditions.append("g.title LIKE ? ESCAPE '\\'")
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.append(f"%{escaped}%")
        if favorites_only:
            conditions.append("g.favorite = 1")
        where = " AND ".join(conditions)
        statement = f"""
            SELECT g.*, r.path, NULLIF(r.archive_member, '') AS archive_member
            FROM games g
            JOIN roms r ON r.rowid = (
                SELECT r2.rowid FROM roms r2
                WHERE r2.game_id = g.id AND r2.available = 1
                ORDER BY r2.last_seen DESC LIMIT 1
            )
            WHERE {where}
            ORDER BY COALESCE(g.last_played, '') DESC, g.title COLLATE NOCASE
        """
        with closing(self.connect()) as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [self._to_game(row) for row in rows]

    def get_game(self, game_id: str) -> Game | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT g.*, r.path, NULLIF(r.archive_member, '') AS archive_member
                FROM games g JOIN roms r ON r.game_id = g.id
                WHERE g.id = ? AND r.available = 1
                ORDER BY r.last_seen DESC LIMIT 1
                """,
                (game_id,),
            ).fetchone()
        return self._to_game(row) if row else None

    def set_favorite(self, game_id: str, favorite: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE games SET favorite = ? WHERE id = ?", (int(favorite), game_id)
            )

    def record_session(
        self,
        *,
        game_id: str,
        started_at: str,
        ended_at: str,
        duration_seconds: int,
        core_filename: str,
        core_version: str | None,
        exit_reason: str,
    ) -> None:
        duration = max(0, duration_seconds)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(
                    game_id, started_at, ended_at, duration_seconds,
                    core_filename, core_version, exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    started_at,
                    ended_at,
                    duration,
                    core_filename,
                    core_version,
                    exit_reason,
                ),
            )
            connection.execute(
                """
                UPDATE games SET
                    playtime_seconds = playtime_seconds + ?,
                    session_count = session_count + 1,
                    last_played = ?
                WHERE id = ?
                """,
                (duration, ended_at, game_id),
            )

    def counts_by_system(self) -> dict[str, int]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT system_id, COUNT(*) AS total FROM games GROUP BY system_id"
            ).fetchall()
        return {str(row["system_id"]): int(row["total"]) for row in rows}

    @staticmethod
    def _to_game(row: sqlite3.Row) -> Game:
        return Game(
            id=str(row["id"]),
            title=str(row["title"]),
            system_id=str(row["system_id"]),
            source_path=Path(str(row["path"])),
            archive_member=str(row["archive_member"]) if row["archive_member"] else None,
            size=int(row["size"]),
            sha256=str(row["sha256"]),
            sha1=str(row["sha1"]),
            crc32=str(row["crc32"]),
            extension=str(row["extension"]),
            detection=str(row["detection"]),
            favorite=bool(row["favorite"]),
            playtime_seconds=int(row["playtime_seconds"]),
            session_count=int(row["session_count"]),
            last_played=str(row["last_played"]) if row["last_played"] else None,
            added_at=str(row["added_at"]),
        )
