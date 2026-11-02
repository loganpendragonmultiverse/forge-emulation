from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from forge_emulation.database import LibraryDatabase
from forge_emulation.location_review import LocationRecord, preview_locations
from forge_emulation.scanner import inspect_file


def record(path: Path, member: str | None = None) -> LocationRecord:
    return LocationRecord("synthetic:1", "Synthetic game", path, member)


def test_location_review_is_read_only_and_does_not_open_roms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "games"
    root.mkdir()
    present = root / "game.nes"
    present.write_bytes(b"SYNTHETIC-ROM-CANARY")
    archive = root / "games.zip"
    archive.write_bytes(b"not parsed by location review")
    missing = root / "missing.nes"
    outside = tmp_path / "outside.nes"

    def no_reads(*args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("ROM contents must not be opened")

    monkeypatch.setattr(Path, "read_bytes", no_reads)
    report = preview_locations(
        [record(present), record(missing), record(outside), record(archive, "game.nes")], root
    )
    assert report.complete
    statuses = {f.location.path.name: f.status for f in report.findings}
    assert statuses == {
        "game.nes": "file present; contents unverified",
        "missing.nes": "missing candidate",
        "outside.nes": "outside selected folder",
        "games.zip": "container present; member unverified",
    }
    assert "not proof of deletion" in report.as_text()
    assert "SYNTHETIC-ROM-CANARY" not in report.as_text()
    assert preview_locations(
        reversed([record(present), record(missing)]), root
    ) == preview_locations([record(missing), record(present)], root)


@pytest.mark.parametrize("mode", ["offline", "file-root", "partial", "exception", "disappeared"])
def test_unavailable_and_partial_roots_never_claim_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    root = tmp_path / "games"
    if mode == "file-root":
        root.write_text("not a folder", encoding="utf-8")
    elif mode != "offline":
        root.mkdir()
    if mode == "partial":

        def incomplete(*args: Any, **kwargs: Any) -> Any:
            kwargs["onerror"](PermissionError("unreadable child"))
            yield str(root), [], []

        monkeypatch.setattr("forge_emulation.location_review.os.walk", incomplete)
    if mode == "exception":

        def interrupted(*args: Any, **kwargs: Any) -> Any:
            raise OSError("disconnected")

        monkeypatch.setattr("forge_emulation.location_review.os.walk", interrupted)
    if mode == "disappeared":
        original = Path.is_dir
        calls = 0

        def availability(path: Path) -> bool:
            nonlocal calls
            if path == root:
                calls += 1
                return calls == 1
            return original(path)

        monkeypatch.setattr(Path, "is_dir", availability)
    report = preview_locations([record(root / "absent.nes")], root)
    assert not report.complete
    assert report.findings[0].status == "unverified; folder unavailable or incomplete"


def test_symlink_not_reported_as_missing(tmp_path: Path) -> None:
    root = tmp_path / "games"
    root.mkdir()
    link = root / "link.nes"
    try:
        link.symlink_to(root / "gone.nes")
    except OSError:
        pytest.skip("symlink creation unavailable")
    report = preview_locations([record(link)], root)
    assert report.findings[0].status == "unverified; symlink not followed"


def test_database_location_review_preserves_history_flags_and_metadata(
    rom_directory: Path, tmp_path: Path
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite3")
    candidates = inspect_file(rom_directory / "forge-test.nes")
    db.import_candidates(candidates)
    game_id = candidates[0].game_id
    db.set_favorite(game_id, True)
    db.set_metadata(game_id, custom_title="My title", artwork_path=None)
    db.record_session(
        game_id=game_id,
        started_at="start",
        ended_at="end",
        duration_seconds=42,
        core_filename="synthetic",
        core_version="test",
        exit_reason="test",
    )
    with db.connect() as c:
        c.execute("UPDATE roms SET available=0")
    with db.connect() as c:
        before = list(c.iterdump())
    records = db.location_records()
    assert len(records) == 1 and records[0].title == "My title"
    preview_locations(records, rom_directory)
    with db.connect() as c:
        assert list(c.iterdump()) == before
        assert c.execute("SELECT available FROM roms").fetchone()[0] == 0
        assert c.execute("SELECT playtime_seconds FROM games").fetchone()[0] == 42
