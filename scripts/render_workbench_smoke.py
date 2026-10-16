"""Render actual workbench controls using original generated cartridge fixtures."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_test_roms import write_test_roms  # noqa: E402

from forge_emulation.database import LibraryDatabase  # noqa: E402
from forge_emulation.paths import app_paths  # noqa: E402
from forge_emulation.scanner import scan_paths  # noqa: E402
from forge_emulation.ui.library_workbench import LibraryWorkbench  # noqa: E402
from forge_emulation.ui.main_window import APP_STYLE, MainWindow, SettingsDialog  # noqa: E402
from forge_emulation.ui.media_dialog import MediaDialog  # noqa: E402


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(APP_STYLE)
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        paths = app_paths(Path(temp))
        paths.ensure()
        roms = Path(temp) / "roms"
        write_test_roms(roms)
        db = LibraryDatabase(paths.database)
        db.import_candidates(scan_paths([roms])[0])
        window = MainWindow(db, paths)
        window.library_tools.bulk_update(
            [g.id for g in db.list_games()][:4], status="Playing", rating=4, add_tags=("Weekend",)
        )
        window.library_tools.save_view("Weekend games", {"tag": "Weekend"})
        window.reload_views()
        workbench = LibraryWorkbench(window.library_tools, db.list_games(), window)
        workbench.table.selectRow(0)
        media = MediaDialog(paths, db.list_games()[0], window)
        media.image_root.mkdir(parents=True)
        image = QImage(384, 240, QImage.Format.Format_RGB32)
        image.fill(QColor("#163D57"))
        image.save(str(media.image_root / "synthetic-preview.png"))
        media.refresh()
        settings = SettingsDialog(window.settings_store, parent=window)
        settings.rewind.setCurrentIndex(2)
        for name, widget in [
            ("workbench", workbench),
            ("media", media),
            ("playback-settings", settings),
            ("library-1.6", window),
        ]:
            widget.show()
            app.processEvents()
            app.processEvents()
            assert widget.grab().save(str(output / (name + ".png")))
            widget.close()
    print(output)


if __name__ == "__main__":
    main()
