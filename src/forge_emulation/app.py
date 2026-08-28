from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .database import LibraryDatabase
from .paths import app_paths
from .ui.main_window import MainWindow


def _configure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def main() -> int:
    paths = app_paths()
    _configure_logging(paths.logs / "application.log")
    application = QApplication(sys.argv)
    application.setApplicationName("ForgeEmulation")
    application.setOrganizationName("Logan Pendragon Multiverse")
    database = LibraryDatabase(paths.database)
    window = MainWindow(database, paths)
    window.show()
    application.processEvents()
    startup_probe = os.environ.get("FORGE_EMULATION_STARTUP_PROBE")
    if startup_probe:
        marker = Path(startup_probe).resolve()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ForgeEmulation-ready\n", encoding="utf-8")
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
