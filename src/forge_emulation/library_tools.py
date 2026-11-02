"""Transactional bulk organization, reusable views and explicit local exports."""

from __future__ import annotations

import csv
import json
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import Game
from .organization import SORTS, STATUSES, Annotation, LibraryOrganizer, annotation, names
from .systems import SYSTEM_BY_ID

VIEW_DEFAULTS: dict[str, Any] = {
    "query": "",
    "system": "",
    "favorites": False,
    "recent": False,
    "status": "",
    "collection": "",
    "tag": "",
    "minimum_rating": 0,
    "unplayed": False,
    "sort": SORTS[0],
}


def validate_view(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - set(VIEW_DEFAULTS):
        raise ValueError("Invalid saved view fields.")
    result = {**VIEW_DEFAULTS, **value}
    for field in ("query", "system", "status", "collection", "tag", "sort"):
        if not isinstance(result[field], str) or len(result[field]) > 200:
            raise ValueError("Invalid saved view text.")
    for field in ("favorites", "recent", "unplayed"):
        if type(result[field]) is not bool:
            raise ValueError("Invalid saved view flag.")
    if result["system"] and result["system"] not in SYSTEM_BY_ID:
        raise ValueError("Unsupported saved view system.")
    if result["status"] and result["status"] not in STATUSES:
        raise ValueError("Invalid saved play status.")
    if result["sort"] not in SORTS or type(result["minimum_rating"]) is not int:
        raise ValueError("Invalid saved sort/rating.")
    if not 0 <= result["minimum_rating"] <= 5:
        raise ValueError("Invalid saved rating.")
    return result


class LibraryTools:
    def __init__(self, organizer: LibraryOrganizer):
        self.organizer = organizer
        with organizer.database.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS saved_views "
                "(name TEXT PRIMARY KEY COLLATE NOCASE, filters TEXT NOT NULL)"
            )

    def views(self) -> dict[str, dict[str, Any]]:
        with closing(self.organizer.database.connect()) as connection:
            rows = connection.execute(
                "SELECT name,filters FROM saved_views ORDER BY name COLLATE NOCASE"
            )
            return {str(row[0]): validate_view(json.loads(row[1])) for row in rows}

    def save_view(self, name: str, value: dict[str, Any]) -> None:
        clean = names([name])[0]
        checked = validate_view(value)
        with self.organizer.database.connect() as connection:
            connection.execute(
                "INSERT INTO saved_views VALUES (?,?) "
                "ON CONFLICT(name) DO UPDATE SET filters=excluded.filters",
                (clean, json.dumps(checked)),
            )

    def delete_view(self, name: str) -> None:
        with self.organizer.database.connect() as connection:
            connection.execute("DELETE FROM saved_views WHERE name=?", (name,))

    def bulk_update(
        self,
        game_ids: list[str],
        *,
        status: str | None = None,
        rating: int | None = None,
        add_tags: tuple[str, ...] = (),
        collection: str | None = None,
        favorite: bool | None = None,
    ) -> int:
        if not game_ids or len(set(game_ids)) != len(game_ids):
            raise ValueError("Select distinct games before applying changes.")
        values = self.organizer.all_annotations()
        checked_tags = names(add_tags)
        checked_collection = names([collection])[0] if collection else None
        updated: dict[str, Annotation] = {}
        for game_id in game_ids:
            value = asdict(values.get(game_id, Annotation()))
            if status is not None:
                value["status"] = status
            if rating is not None:
                value["rating"] = rating
            value["tags"] = names([*value["tags"], *checked_tags])
            if checked_collection:
                value["collections"] = names([*value["collections"], checked_collection])
            updated[game_id] = annotation(value)
        with self.organizer.database.connect() as connection:
            # Validate every target in the same transaction before the first write.
            for game_id in game_ids:
                if not connection.execute("SELECT 1 FROM games WHERE id=?", (game_id,)).fetchone():
                    raise ValueError("A selected game is no longer in the library.")
            for game_id, checked_value in updated.items():
                self.organizer._write(connection, game_id, checked_value)
                if favorite is not None:
                    connection.execute(
                        "UPDATE games SET favorite=? WHERE id=?", (int(favorite), game_id)
                    )
        return len(updated)

    def export_csv(self, games: list[Game], target: Path, *, include_notes: bool = False) -> int:
        values = self.organizer.all_annotations()

        def safe(value: str) -> str:
            # Neutralize formulas even when a spreadsheet ignores leading whitespace.
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value

        fields = [
            "title",
            "system",
            "game_id",
            "status",
            "rating",
            "tags",
            "collections",
            "playtime_seconds",
            "session_count",
        ]
        if include_notes:
            fields.append("notes")
        with target.open("x", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(fields)
            for game in games:
                value = values.get(game.id, Annotation())
                row: list[str | int] = [
                    safe(game.display_title),
                    game.system_id,
                    safe(game.id),
                    value.status,
                    value.rating,
                    safe(", ".join(value.tags)),
                    safe(", ".join(value.collections)),
                    game.playtime_seconds,
                    game.session_count,
                ]
                if include_notes:
                    row.append(safe(value.notes))
                writer.writerow(row)
        return len(games)
