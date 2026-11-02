from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest

from forge_emulation.database import LibraryDatabase
from forge_emulation.organization import Annotation, LibraryOrganizer, annotation, names
from forge_emulation.scanner import scan_paths


@pytest.fixture
def library(rom_directory: Path, tmp_path: Path) -> tuple[LibraryDatabase, LibraryOrganizer]:
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    candidates, errors = scan_paths([rom_directory])
    assert not errors
    database.import_candidates(candidates)
    return database, LibraryOrganizer(database)


def test_additive_migration_preserves_library_and_rescans(library):
    database, organizer = library
    game = database.list_games()[0]
    before = database.location_records()
    database.set_favorite(game.id, True)
    organizer.save(game.id, Annotation("Playing", 4, "Next: castle", ("Co-op",), ("Weekend",)))
    reopened = LibraryOrganizer(LibraryDatabase(database.path))
    assert reopened.get(game.id).notes == "Next: castle"
    assert database.get_game(game.id).favorite
    assert before == database.location_records()
    assert database.integrity_check() == "ok"


def test_collection_lifecycle_keeps_games_history_and_notes(library):
    database, organizer = library
    game = database.list_games()[0]
    organizer.create_collection("Weekend")
    organizer.save(game.id, Annotation(notes="keep", collections=("Weekend", "Other")))
    organizer.rename_collection("weekend", "Saturday")
    assert organizer.get(game.id).collections == ("Other", "Saturday")
    assert organizer.collections() == ["Other", "Saturday"]
    with pytest.raises(sqlite3.IntegrityError):
        organizer.rename_collection("Saturday", "Other")
    assert organizer.get(game.id).collections == ("Other", "Saturday")
    organizer.delete_collection("saturday")
    assert organizer.get(game.id).notes == "keep"
    assert organizer.get(game.id).collections == ("Other",)
    assert len(database.list_games()) == 9
    with pytest.raises(ValueError):
        organizer.rename_collection("Missing", "New")


@pytest.mark.parametrize(
    "value",
    [
        {"status": "invented", "rating": 0, "notes": "", "tags": [], "collections": []},
        {"status": "Unplayed", "rating": True, "notes": "", "tags": [], "collections": []},
        {"status": "Playing", "rating": 6, "notes": "", "tags": [], "collections": []},
        {"status": "Playing", "rating": 1, "notes": "a" * 10001, "tags": [], "collections": []},
        None,
        [],
        {},
    ],
)
def test_rejects_invalid_annotations(value):
    with pytest.raises(ValueError):
        annotation(value)


@pytest.mark.parametrize("value", [None, "", [""], ["a" * 81], ["a\nb"], ["x"] * 51, [1]])
def test_rejects_invalid_names(value):
    with pytest.raises(ValueError):
        names(value)


def test_names_normalize_without_case_duplicates():
    assert names([" Weekend ", "weekend", "Arcade"]) == ("Arcade", "Weekend")


def test_composable_filters_and_stable_sorting(library):
    database, organizer = library
    games = database.list_games()
    first, second = games[:2]
    organizer.save(first.id, Annotation("Completed", 5, tags=("Puzzle",), collections=("Weekend",)))
    organizer.save(second.id, Annotation("Playing", 2))
    assert organizer.select(
        games, status="Completed", collection="weekend", tag="PUZZLE", minimum_rating=4
    ) == [first]
    assert organizer.select(games, minimum_rating=5) == [first]
    assert organizer.select(games, tag="missing") == []
    assert organizer.select(games, sort="Highest rated")[0] == first
    database.record_session(
        game_id=second.id,
        started_at="2026-10-16T12:00:00+00:00",
        ended_at="2026-10-16T12:01:00+00:00",
        duration_seconds=60,
        core_filename="test",
        core_version="1",
        exit_reason="user-exit",
    )
    games = database.list_games()
    assert organizer.select(games, sort="Most played")[0].id == second.id
    assert organizer.select(games, sort="Recent activity")[0].id == second.id
    assert len(organizer.select(games, unplayed=True)) == 8
    assert len(organizer.select(games, sort="Recently added")) == 9
    titles = [g.display_title.casefold() for g in organizer.select(games, sort="Title A–Z")]
    assert titles == sorted(titles)


def test_session_history_is_read_only_and_bounded(library):
    database, organizer = library
    game = database.list_games()[0]
    for minute in range(3):
        database.record_session(
            game_id=game.id,
            started_at="start",
            ended_at=f"end-{minute}",
            duration_seconds=minute,
            core_filename="test",
            core_version=None,
            exit_reason="user-exit",
        )
    assert len(organizer.history(limit=2)) == 2
    assert organizer.history(game.id)[0]["ended_at"] == "end-2"
    assert organizer.history("unknown") == []
    assert organizer.history(limit=-1) == []
    assert database.get_game(game.id).session_count == 3


def test_exchange_matches_content_and_preserves_nonorganization_data(library, tmp_path):
    database, organizer = library
    game = database.list_games()[0]
    organizer.save(game.id, Annotation("Completed", 5, "private note", ("Puzzle",), ("Weekend",)))
    source = tmp_path / "organization.json"
    before = database.location_records()
    assert organizer.export(source) == 9
    text = source.read_text()
    assert str(game.source_path) not in text
    assert "artwork_path" not in text and "playtime" not in text and "archive_member" not in text
    with pytest.raises(FileExistsError):
        organizer.export(source)
    organizer.save(game.id, Annotation())
    preview = organizer.read_import(source)
    assert organizer.get(game.id) == Annotation()  # preview never writes
    assert len(preview["matches"]) == 9
    assert organizer.apply_import(preview) == 9
    assert organizer.get(game.id).notes == "private note"
    assert database.location_records() == before


def test_exchange_validation_is_all_or_nothing(library, tmp_path):
    database, organizer = library
    game = database.list_games()[0]
    path = tmp_path / "data.json"
    organizer.export(path)
    document = json.loads(path.read_text())
    document["games"][0]["sha256"] = "wrong"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        organizer.read_import(path)
    document["games"] = [document["games"][0], document["games"][0]]
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        organizer.read_import(path)
    document["games"] = [{"id": "unknown", **asdict(Annotation())}]
    path.write_text(json.dumps(document))
    preview = organizer.read_import(path)
    assert preview["unknown"] == 1 and not preview["matches"]
    document["schema"] = 2
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        organizer.read_import(path)
    path.write_text("x" * (8 * 1024 * 1024 + 1))
    with pytest.raises(ValueError):
        organizer.read_import(path)
    assert organizer.get(game.id) == Annotation()


def test_import_transaction_rolls_back_collections_on_missing_game(library):
    database, organizer = library
    with pytest.raises(sqlite3.IntegrityError):
        organizer.apply_import(
            {"collections": ["Should roll back"], "matches": {"missing": Annotation()}}
        )
    assert organizer.collections() == []
