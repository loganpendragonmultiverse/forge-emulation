from __future__ import annotations

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from forge_emulation.database import LibraryDatabase  # noqa: E402
from forge_emulation.paths import app_paths  # noqa: E402
from forge_emulation.scanner import scan_paths  # noqa: E402
from forge_emulation.ui.library_workbench import LibraryWorkbench  # noqa: E402
from forge_emulation.ui.main_window import MainWindow, SettingsDialog  # noqa: E402
from forge_emulation.ui.media_dialog import MediaDialog  # noqa: E402


def test_workbench_views_pagination_and_settings(tmp_path, rom_directory, monkeypatch):
    app = QApplication.instance() or QApplication([])
    paths = app_paths(tmp_path)
    paths.ensure()
    database = LibraryDatabase(paths.database)
    database.import_candidates(scan_paths([rom_directory])[0])
    window = MainWindow(database, paths)
    window.page_size = 3
    window.refresh()
    assert window.page_label.text() == "Page 1 / 3"
    assert len(window.visible_games) == 9
    window.change_page(1)
    assert window.page_label.text() == "Page 2 / 3"
    window.library_tools.save_view("NES night", {"system": "nes", "query": "forge"})
    window.reload_views()
    window.saved_views.setCurrentIndex(window.saved_views.findData("NES night"))
    assert window.current_system == "nes" and window.search.text() == "forge"
    assert len(window.visible_games) == 1 and window.page_index == 0
    window._select_filter(None)
    window.search.clear()
    dialog = LibraryWorkbench(window.library_tools, window.visible_games, window)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    dialog.table.selectAll()
    dialog.status.setCurrentText("Completed")
    dialog.rating.setCurrentIndex(6)
    dialog.tags.setText("Weekend")
    dialog.apply()
    assert len(dialog.selected()) == 9
    assert all(window.organizer.get(g.id).status == "Completed" for g in window.visible_games)
    assert all(window.organizer.get(g.id).rating == 5 for g in window.visible_games)
    assert dialog.table.item(0, 5).text() == "Weekend"
    current = replace(
        window.settings_store.global_settings,
        rewind_seconds=30,
        fast_forward_speed=4,
        suspend_on_exit=True,
        resume_on_launch=True,
    )
    window.settings_store.set_global(current)
    settings = SettingsDialog(window.settings_store)
    settings._save()
    assert window.settings_store.global_settings == current
    window._set_fullscreen_default(True)
    assert window.settings_store.global_settings.rewind_seconds == 30
    media = MediaDialog(paths, window.visible_games[0], window)
    assert media.list.count() == 0 and "No states" in media.info.text()
    for widget in (window, dialog, settings, media):
        widget.show()
        app.processEvents()
        widget.close()
