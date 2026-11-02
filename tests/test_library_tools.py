from __future__ import annotations

import csv

import pytest

from forge_emulation.database import LibraryDatabase
from forge_emulation.library_tools import LibraryTools, validate_view
from forge_emulation.organization import Annotation, LibraryOrganizer
from forge_emulation.scanner import scan_paths


@pytest.fixture
def tools(tmp_path, rom_directory):
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    database.import_candidates(scan_paths([rom_directory])[0])
    return LibraryTools(LibraryOrganizer(database))


def test_bulk_changes_preserve_notes_and_existing_memberships(tools):
    games = tools.organizer.database.list_games()
    tools.organizer.save(
        games[0].id, Annotation(notes="keep", tags=("Old",), collections=("Original",))
    )
    ids = [g.id for g in games[:2]]
    assert (
        tools.bulk_update(
            ids, status="Playing", rating=4, add_tags=("New",), collection="Weekend", favorite=True
        )
        == 2
    )
    first = tools.organizer.get(ids[0])
    assert first.notes == "keep" and first.tags == ("New", "Old")
    assert first.collections == ("Original", "Weekend")
    assert all(tools.organizer.database.get_game(i).favorite for i in ids)
    tools.bulk_update(ids, favorite=False, rating=0)
    assert not tools.organizer.database.get_game(ids[0]).favorite
    assert tools.organizer.get(ids[0]).rating == 0


def test_bulk_validation_and_missing_game_do_not_partially_write(tools):
    game = tools.organizer.database.list_games()[0]
    before = tools.organizer.get(game.id)
    for ids, kwargs in [
        ([], {}),
        ([game.id, game.id], {}),
        ([game.id, "missing"], {"rating": 5}),
        ([game.id], {"status": "invalid"}),
        ([game.id], {"rating": 6}),
    ]:
        with pytest.raises(ValueError):
            tools.bulk_update(ids, **kwargs)
        assert tools.organizer.get(game.id) == before


def test_saved_views_roundtrip_case_insensitive_update_and_delete(tools):
    tools.save_view("Weekend", {"status": "Playing", "tag": "Puzzle", "minimum_rating": 3})
    assert tools.views()["Weekend"]["minimum_rating"] == 3
    tools.save_view("weekend", {"system": "nes", "unplayed": True})
    assert len(tools.views()) == 1 and tools.views()["Weekend"]["system"] == "nes"
    tools.delete_view("WEEKEND")
    assert tools.views() == {}


@pytest.mark.parametrize(
    "value",
    [
        None,
        {"bad": 1},
        {"sort": "unknown"},
        {"system": "unknown"},
        {"unplayed": 1},
        {"status": "Bad"},
        {"minimum_rating": True},
        {"minimum_rating": 7},
        {"tag": "x" * 201},
    ],
)
def test_invalid_saved_view_rejected(value):
    with pytest.raises(ValueError):
        validate_view(value)


def test_csv_excludes_paths_and_notes_unless_requested_and_neutralizes_formulas(tools, tmp_path):
    game = tools.organizer.database.list_games()[0]
    tools.organizer.database.set_metadata(game.id, custom_title=" =SUM(1,2)", artwork_path=None)
    tools.organizer.save(game.id, Annotation(notes="\t=PRIVATE()", tags=("@formula",)))
    game = tools.organizer.database.get_game(game.id)
    target = tmp_path / "library.csv"
    tools.export_csv([game], target)
    with target.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["title"].startswith("'") and rows[0]["tags"].startswith("'")
    assert "notes" not in rows[0] and str(game.source_path) not in target.read_text()
    with pytest.raises(FileExistsError):
        tools.export_csv([game], target)
    tools.export_csv([game], tmp_path / "notes.csv", include_notes=True)
    assert "'\t=PRIVATE()" in (tmp_path / "notes.csv").read_text()
