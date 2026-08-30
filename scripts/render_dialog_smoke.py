from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from forge_emulation.paths import app_paths  # noqa: E402
from forge_emulation.settings import SettingsStore  # noqa: E402
from forge_emulation.ui.main_window import APP_STYLE, SettingsDialog  # noqa: E402


def _capture(widget: SettingsDialog | QMessageBox, output: Path) -> None:
    widget.show()
    application = QApplication.instance()
    if application is None:
        raise RuntimeError("QApplication is not running")
    application.processEvents()
    application.processEvents()
    if not widget.grab().save(str(output)):
        raise RuntimeError(f"Could not save {output}")
    widget.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Render deterministic dialog smoke images.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    application = QApplication.instance() or QApplication([])
    if not QFontDatabase.families():
        for filename in ("segoeui.ttf", "seguisb.ttf", "seguisym.ttf"):
            QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / filename))
    application.setStyleSheet(APP_STYLE)
    with tempfile.TemporaryDirectory(prefix="forge-emulation-dialogs-") as temporary:
        paths = app_paths(Path(temporary) / "portable")
        settings = SettingsDialog(SettingsStore(paths.preferences))
        _capture(settings, args.output / "display-audio.png")

        backup = QMessageBox()
        backup.setWindowTitle("Backup & restore")
        backup.setText("Export a complete local backup, or restore one?")
        backup.addButton("Export backup", QMessageBox.ButtonRole.AcceptRole)
        backup.addButton("Restore backup", QMessageBox.ButtonRole.ActionRole)
        backup.addButton(QMessageBox.StandardButton.Cancel)
        _capture(backup, args.output / "backup-restore.png")

    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
