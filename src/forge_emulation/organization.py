"""Local library organization and bounded, content-addressed metadata exchange."""

from __future__ import annotations

import json
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .database import LibraryDatabase
from .models import Game

STATUSES = ("Unplayed", "Playing", "Completed", "On hold", "Abandoned")
SORTS = ("Recent activity", "Title A–Z", "Most played", "Recently added", "Highest rated")
MAX_EXCHANGE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class Annotation:
    status: str = "Unplayed"
    rating: int = 0
    notes: str = ""
    tags: tuple[str, ...] = ()
    collections: tuple[str, ...] = ()


def names(values: Any, limit: int = 50) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > limit:
        raise ValueError(f"Use at most {limit} names.")
    result: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
            raise ValueError("Names must contain 1–80 characters.")
        clean = value.strip()
        if any(ord(c) < 32 for c in clean):
            raise ValueError("Names cannot contain control characters.")
        result.setdefault(clean.casefold(), clean)
    return tuple(sorted(result.values(), key=str.casefold))


def annotation(value: Any) -> Annotation:
    if not isinstance(value, dict):
        raise ValueError("Invalid game metadata.")
    status, rating, notes = value.get("status"), value.get("rating"), value.get("notes")
    if status not in STATUSES or type(rating) is not int or not 0 <= rating <= 5:
        raise ValueError("Use a valid play status and a rating from 0 to 5.")
    if not isinstance(notes, str) or len(notes) > 10000:
        raise ValueError("Notes must contain at most 10,000 characters.")
    return Annotation(
        status, rating, notes, names(value.get("tags")), names(value.get("collections"))
    )


class LibraryOrganizer:
    def __init__(self, database: LibraryDatabase):
        self.database = database
        with database.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS annotations (
                    game_id TEXT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
                    status TEXT NOT NULL, rating INTEGER NOT NULL, notes TEXT NOT NULL,
                    tags TEXT NOT NULL, collections TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collections (
                    name TEXT PRIMARY KEY COLLATE NOCASE
                );
            """)

    def all_annotations(self) -> dict[str, Annotation]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute("SELECT * FROM annotations").fetchall()
        return {
            str(row["game_id"]): Annotation(
                str(row["status"]),
                int(row["rating"]),
                str(row["notes"]),
                tuple(json.loads(row["tags"])),
                tuple(json.loads(row["collections"])),
            )
            for row in rows
        }

    def get(self, game_id: str) -> Annotation:
        return self.all_annotations().get(game_id, Annotation())

    @staticmethod
    def _write(connection: Any, game_id: str, value: Annotation) -> None:
        connection.execute(
            "INSERT INTO annotations VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(game_id) DO UPDATE SET status=excluded.status, rating=excluded.rating, "
            "notes=excluded.notes, tags=excluded.tags, collections=excluded.collections",
            (
                game_id,
                value.status,
                value.rating,
                value.notes,
                json.dumps(value.tags),
                json.dumps(value.collections),
            ),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO collections VALUES (?)", [(name,) for name in value.collections]
        )

    def save(self, game_id: str, value: Annotation) -> None:
        checked = annotation(asdict(value))
        with self.database.connect() as connection:
            self._write(connection, game_id, checked)

    def collections(self) -> list[str]:
        with closing(self.database.connect()) as connection:
            return [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM collections ORDER BY name COLLATE NOCASE"
                )
            ]

    def create_collection(self, name: str) -> None:
        clean = names([name])[0]
        with self.database.connect() as connection:
            connection.execute("INSERT INTO collections VALUES (?)", (clean,))

    def rename_collection(self, old: str, new: str) -> None:
        clean = names([new])[0]
        with self.database.connect() as connection:
            cursor = connection.execute("UPDATE collections SET name=? WHERE name=?", (clean, old))
            if cursor.rowcount != 1:
                raise ValueError("Collection no longer exists.")
            for game_id, value in self.all_annotations().items():
                if any(item.casefold() == old.casefold() for item in value.collections):
                    updated = asdict(value)
                    updated["collections"] = [
                        clean if item.casefold() == old.casefold() else item
                        for item in value.collections
                    ]
                    self._write(connection, game_id, annotation(updated))

    def delete_collection(self, name: str) -> None:
        with self.database.connect() as connection:
            for game_id, value in self.all_annotations().items():
                updated = asdict(value)
                updated["collections"] = [
                    item for item in value.collections if item.casefold() != name.casefold()
                ]
                self._write(connection, game_id, annotation(updated))
            connection.execute("DELETE FROM collections WHERE name=?", (name,))

    def select(
        self,
        games: list[Game],
        *,
        status: str = "",
        collection: str = "",
        tag: str = "",
        minimum_rating: int = 0,
        unplayed: bool = False,
        sort: str = SORTS[0],
    ) -> list[Game]:
        values = self.all_annotations()
        result = []
        for game in games:
            value = values.get(game.id, Annotation())
            if status and value.status != status:
                continue
            if collection and collection.casefold() not in [
                n.casefold() for n in value.collections
            ]:
                continue
            if tag and tag.casefold() not in [n.casefold() for n in value.tags]:
                continue
            if value.rating < minimum_rating or (unplayed and game.session_count):
                continue
            result.append(game)
        result.sort(key=lambda g: (g.display_title.casefold(), g.id))
        if sort == "Most played":
            result.sort(key=lambda g: g.playtime_seconds, reverse=True)
        elif sort == "Recently added":
            result.sort(key=lambda g: g.added_at, reverse=True)
        elif sort == "Highest rated":
            result.sort(key=lambda g: values.get(g.id, Annotation()).rating, reverse=True)
        elif sort == "Recent activity":
            result.sort(key=lambda g: g.last_played or "", reverse=True)
        return result

    def history(self, game_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                "SELECT COALESCE(g.custom_title,g.title) AS title, g.system_id, s.* "
                "FROM sessions s JOIN games g ON g.id=s.game_id "
                "WHERE (? IS NULL OR s.game_id=?) ORDER BY s.ended_at DESC, s.id DESC LIMIT ?",
                (game_id, game_id, max(0, min(limit, 1000))),
            ).fetchall()
        return [dict(row) for row in rows]

    def export(self, target: Path) -> int:
        # Paths, artwork, ROMs, saves, and play history are deliberately absent.
        with closing(self.database.connect()) as connection:
            games = connection.execute("SELECT id, system_id, sha256 FROM games").fetchall()
        values = self.all_annotations()
        document = {
            "format": "ForgeEmulation organization",
            "schema": 1,
            "collections": self.collections(),
            "games": [
                {
                    "id": str(g["id"]),
                    "system_id": str(g["system_id"]),
                    "sha256": str(g["sha256"]),
                    **asdict(values.get(str(g["id"]), Annotation())),
                }
                for g in games
            ],
        }
        text = json.dumps(document, indent=2, ensure_ascii=False)
        if len(text.encode("utf-8")) > MAX_EXCHANGE_BYTES:
            raise ValueError("Organization export exceeds the 8 MiB exchange limit.")
        with target.open("x", encoding="utf-8") as handle:
            handle.write(text)
        return len(games)

    def read_import(self, source: Path) -> dict[str, Any]:
        if source.stat().st_size > MAX_EXCHANGE_BYTES:
            raise ValueError("Organization files must be smaller than 8 MiB.")
        document = json.loads(source.read_text(encoding="utf-8"))
        if (
            not isinstance(document, dict)
            or document.get("schema") != 1
            or document.get("format") != "ForgeEmulation organization"
        ):
            raise ValueError("Unsupported organization format.")
        collection_names = names(document.get("collections"), limit=5000)
        entries = document.get("games")
        if not isinstance(entries, list) or len(entries) > 20000:
            raise ValueError("Use at most 20,000 game entries.")
        with closing(self.database.connect()) as connection:
            identities = {
                str(r[0]): (str(r[1]), str(r[2]))
                for r in connection.execute("SELECT id,system_id,sha256 FROM games")
            }
        matches: dict[str, Annotation] = {}
        seen: set[str] = set()
        unknown = 0
        for entry in entries:
            value = annotation(entry)
            game_id = entry.get("id")
            if not isinstance(game_id, str) or not game_id or len(game_id) > 160 or game_id in seen:
                raise ValueError("Invalid or duplicate game identity.")
            seen.add(game_id)
            if game_id not in identities:
                unknown += 1
                continue
            if identities[game_id] != (entry.get("system_id"), entry.get("sha256")):
                raise ValueError("Game content identity does not match the library.")
            matches[game_id] = value
        return {"matches": matches, "unknown": unknown, "collections": collection_names}

    def apply_import(self, preview: dict[str, Any]) -> int:
        # Recheck current identities by accepting only existing IDs in the transaction.
        matches: dict[str, Annotation] = preview["matches"]
        with self.database.connect() as connection:
            for name in names(preview["collections"], limit=5000):
                connection.execute("INSERT OR IGNORE INTO collections VALUES (?)", (name,))
            for game_id, value in matches.items():
                self._write(connection, game_id, annotation(asdict(value)))
        return len(matches)
