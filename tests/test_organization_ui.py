"""Offscreen Qt acceptance for organization flows; no physical-controller claims."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PySide6.QtWidgets import QApplication  # noqa: E402

from forge_emulation.database import LibraryDatabase  # noqa: E402
from forge_emulation.organization import Annotation  # noqa: E402
from forge_emulation.paths import app_paths  # noqa: E402
from forge_emulation.scanner import scan_paths  # noqa: E402
from forge_emulation.ui.main_window import MainWindow  # noqa: E402
from forge_emulation.ui.organization_dialogs import (  # noqa: E402
    AnnotationDialog,
    CollectionsDialog,
    HistoryDialog,
)


def test_organization_window_flow(tmp_path: Path, rom_directory: Path) -> None:
    app = QApplication.instance() or QApplication([])
    paths = app_paths(tmp_path)
    paths.ensure()
    database = LibraryDatabase(paths.database)
    database.import_candidates(scan_paths([rom_directory])[0])
    window = MainWindow(database, paths)
    game = database.list_games()[0]
    window.organizer.create_collection("Weekend")
    window.reload_collections()
    dialog = AnnotationDialog(window.organizer, game, window)
    dialog.status.setCurrentText("Completed")
    dialog.rating.setValue(5)
    dialog.tags.setText("Puzzle, Weekend")
    dialog.notes.setPlainText("Try the second route")
    dialog.collections.item(0).setSelected(True)
    dialog.save()
    assert dialog.result() == dialog.DialogCode.Accepted
    window.refresh()
    window.collection_filter.setCurrentText("Weekend")
    window.status_filter.setCurrentText("Completed")
    window.tag_filter.setText("Puzzle")
    window.rating_filter.setCurrentIndex(5)
    assert window.section_title.text() == "1 game"
    window.status_filter.setCurrentText("Playing")
    assert window.section_title.text() == "0 games"
    window.clear_organization_filters()
    assert window.section_title.text() == "9 games"
    manager = CollectionsDialog(window.organizer, window)
    assert manager.list.count() == 1
    history = HistoryDialog(window.organizer, game, window)
    assert history.windowTitle().startswith("Play history")
    window.organizer.save(game.id, Annotation())
    window._select_filter("documentation")
    assert window.organization_controls.isHidden()
    window._select_filter(None)
    window.show()
    app.processEvents()
    window.close()
    manager.close()
    history.close()
