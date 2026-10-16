from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..media_manager import checked_media, export_media, recoverable_remove
from ..models import Game
from ..paths import AppPaths
from ..state_browser import state_metadata
from ..systems import SYSTEM_BY_ID


class MediaDialog(QDialog):
    def __init__(self, paths: AppPaths, game: Game, parent: QWidget | None = None):
        super().__init__(parent)
        self.paths, self.game = paths, game
        self.setWindowTitle("States & screenshots · " + game.display_title)
        self.resize(800, 650)
        key = game.sha256[:24]
        self.state_root = paths.states / game.system_id / key
        self.image_root = paths.screenshots / game.system_id / key
        self.files: list[tuple[Path, Path]] = []
        self.reviewed_digest = ""
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.preview)
        layout.addWidget(self.list, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.image)
        layout.addWidget(scroll, 1)
        actions = QHBoxLayout()
        for title, callback in [
            ("Export selected", self.export),
            ("Move to recovery", self.remove),
            ("Done", self.accept),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.refresh()

    def refresh(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        self.files = []
        for root, suffix in [(self.state_root, ".state"), (self.image_root, ".png")]:
            if root.is_symlink():
                continue
            for path in sorted(root.glob("*" + suffix)):
                if not path.is_symlink() and path.is_file():
                    self.files.append((path, root))
                    self.list.addItem(
                        ("State · " if suffix == ".state" else "Screenshot · ") + path.name
                    )
        self.list.blockSignals(False)
        if self.files:
            self.list.setCurrentRow(0)
        else:
            self.info.setText("No states or screenshots for this game yet.")
            self.image.clear()

    def preview(self, row: int) -> None:
        self.image.clear()
        self.reviewed_digest = ""
        if not 0 <= row < len(self.files):
            return
        path, root = self.files[row]
        try:
            self.reviewed_digest = checked_media(path, root)
            if path.suffix == ".state":
                value = state_metadata(path)
                system = SYSTEM_BY_ID[self.game.system_id]
                compatible = (value["game_id"], value["core"], value["core_version"]) == (
                    self.game.id,
                    system.core_name,
                    system.core_version,
                )
                self.info.setText(
                    f"{path.name} · {value['created_at']}\n"
                    + (
                        "Game/core version matches"
                        if compatible
                        else "Different game/core/version; do not load this state"
                    )
                )
                image = path.with_suffix(".png")
            else:
                self.info.setText(path.name + " · " + str(path.stat().st_size) + " bytes")
                image = path
            if (
                image.is_file()
                and not image.is_symlink()
                and image.stat().st_size < 2 * 1024 * 1024
            ):
                self.image.setPixmap(
                    QPixmap(str(image)).scaled(
                        640,
                        280,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        except (OSError, ValueError) as error:
            self.info.setText(str(error))

    def export(self) -> None:
        row = self.list.currentRow()
        if not 0 <= row < len(self.files):
            return
        path, root = self.files[row]
        filename, _ = QFileDialog.getSaveFileName(self, "Export game media", path.name)
        if filename:
            try:
                export_media(path, root, Path(filename))
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Export failed", str(error))

    def remove(self) -> None:
        row = self.list.currentRow()
        if not 0 <= row < len(self.files) or not self.reviewed_digest:
            return
        if (
            QMessageBox.question(
                self,
                "Move selected media to recovery",
                "Move this file out of the game folder? "
                "A state thumbnail moves with its state. Recovery files stay in backups.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        path, root = self.files[row]
        try:
            destination = recoverable_remove(self.paths, path, root, self.reviewed_digest)
            self.refresh()
            QMessageBox.information(self, "Moved to recovery", str(destination))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Recovery operation interrupted", str(error))
