"""Render organization surfaces using only original generated cartridges."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from generate_test_roms import write_test_roms  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from forge_emulation.database import LibraryDatabase  # noqa: E402
from forge_emulation.organization import Annotation  # noqa: E402
from forge_emulation.paths import app_paths  # noqa: E402
from forge_emulation.scanner import scan_paths  # noqa: E402
from forge_emulation.ui.main_window import MainWindow  # noqa: E402
from forge_emulation.ui.organization_dialogs import AnnotationDialog  # noqa: E402

destination = Path(sys.argv[1])
destination.mkdir(parents=True, exist_ok=True)
app = QApplication([])
with tempfile.TemporaryDirectory() as directory:
    paths = app_paths(Path(directory))
    roms = Path(directory) / "roms"
    write_test_roms(roms)
    database = LibraryDatabase(paths.database)
    database.import_candidates(scan_paths([roms])[0])
    window = MainWindow(database, paths)
    window.organizer.create_collection("Weekend queue")
    games = database.list_games()
    for index, game in enumerate(games):
        window.organizer.save(
            game.id,
            Annotation(
                "Completed" if index == 0 else "Playing" if index < 4 else "Unplayed",
                5 if index == 0 else 3 if index < 4 else 0,
                "Try the alternate route next time.",
                ("Original fixture",),
                ("Weekend queue",) if index < 4 else (),
            ),
        )
    window.reload_collections()
    window.refresh()
    window.show()
    app.processEvents()
    assert window.grab().save(str(destination / "organization.png"))
    dialog = AnnotationDialog(window.organizer, games[0], window)
    dialog.show()
    app.processEvents()
    assert dialog.grab().save(str(destination / "organization-editor.png"))
    dialog.close()
    window.close()
