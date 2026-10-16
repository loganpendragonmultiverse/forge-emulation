"""Explicit content-verified location additions; never rename, delete or copy ROMs."""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .database import LibraryDatabase, _now
from .models import GameCandidate
from .scanner import inspect_file, scan_paths


@dataclass(frozen=True)
class RelinkPlan:
    revision: str
    matches: tuple[GameCandidate, ...]
    unmatched: int
    errors: tuple[str, ...]


def library_revision(database: LibraryDatabase) -> str:
    with closing(database.connect()) as connection:
        locations = [
            tuple(row)
            for row in connection.execute(
                "SELECT game_id,path,archive_member,available,last_seen FROM roms "
                "ORDER BY game_id,path,archive_member"
            )
        ]
        identities = [
            tuple(row)
            for row in connection.execute("SELECT id,system_id,sha256 FROM games ORDER BY id")
        ]
    return hashlib.sha256(json.dumps([locations, identities]).encode()).hexdigest()


def preview_relink(database: LibraryDatabase, root: Path) -> RelinkPlan:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Choose an available regular game folder.")
    revision = library_revision(database)
    with closing(database.connect()) as connection:
        known = {str(row[0]) for row in connection.execute("SELECT id FROM games")}
    candidates, errors = scan_paths([root])
    matches = tuple(c for c in candidates if c.game_id in known)
    return RelinkPlan(revision, matches, len(candidates) - len(matches), tuple(errors))


def apply_relink(database: LibraryDatabase, plan: RelinkPlan) -> int:
    if plan.errors:
        raise ValueError("The scan was incomplete. Resolve its errors and review a new preview.")
    if library_revision(database) != plan.revision:
        raise ValueError("Library locations changed after preview. Review a new plan.")
    checked: list[GameCandidate] = []
    for candidate in plan.matches:
        if candidate.source_path.is_symlink():
            raise ValueError("A replacement became a link. Review a new preview.")
        verified = inspect_file(candidate.source_path)
        match = next(
            (
                c
                for c in verified
                if c.game_id == candidate.game_id
                and c.archive_member == candidate.archive_member
                and c.sha256 == candidate.sha256
            ),
            None,
        )
        if match is None:
            raise ValueError("Replacement content changed after preview; no locations were added.")
        checked.append(match)
    with database.connect() as connection:
        # Recheck the complete location revision after content verification and before writes.
        connection.execute("BEGIN IMMEDIATE")
        if library_revision(database) != plan.revision:
            raise ValueError("Library changed while replacements were verified.")
        for candidate in checked:
            identity = connection.execute(
                "SELECT sha256,system_id FROM games WHERE id=?", (candidate.game_id,)
            ).fetchone()
            if identity is None or tuple(identity) != (candidate.sha256, candidate.system_id):
                raise ValueError("The replacement no longer matches a known game.")
        for candidate in checked:
            connection.execute(
                "INSERT INTO roms(path,archive_member,game_id,available,last_seen) "
                "VALUES(?,?,?,1,?) "
                "ON CONFLICT(path,archive_member) DO UPDATE SET "
                "game_id=excluded.game_id,available=1,last_seen=excluded.last_seen",
                (
                    str(candidate.source_path),
                    candidate.archive_member or "",
                    candidate.game_id,
                    _now(),
                ),
            )
    return len(checked)
