from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..models import Game
from ..organization import STATUSES, Annotation, LibraryOrganizer


class AnnotationDialog(QDialog):
    def __init__(self, organizer: LibraryOrganizer, game: Game, parent: QWidget | None = None):
        super().__init__(parent)
        self.organizer, self.game = organizer, game
        self.setWindowTitle("Organize · " + game.display_title)
        self.resize(620, 640)
        value = organizer.get(game.id)
        layout = QVBoxLayout(self)
        heading = QLabel(game.display_title)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        form = QFormLayout()
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        self.status.setCurrentText(value.status)
        self.rating = QSpinBox()
        self.rating.setRange(0, 5)
        self.rating.setSpecialValueText("Unrated")
        self.rating.setValue(value.rating)
        self.tags = QLineEdit(", ".join(value.tags))
        self.tags.setPlaceholderText("Co-op, Weekend, Puzzle")
        form.addRow("Play status", self.status)
        form.addRow("Rating / 5", self.rating)
        form.addRow("Tags (comma separated)", self.tags)
        layout.addLayout(form)
        layout.addWidget(QLabel("Notes · included in organization exports"))
        self.notes = QPlainTextEdit(value.notes)
        layout.addWidget(self.notes, 1)
        layout.addWidget(QLabel("Collections · select any number"))
        self.collections = QListWidget()
        self.collections.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.collections.addItems(organizer.collections())
        for index in range(self.collections.count()):
            item = self.collections.item(index)
            item.setSelected(item.text().casefold() in [n.casefold() for n in value.collections])
        layout.addWidget(self.collections, 1)
        actions = QHBoxLayout()
        save = QPushButton("Save organization")
        save.setObjectName("Primary")
        save.clicked.connect(self.save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(save)
        actions.addWidget(cancel)
        layout.addLayout(actions)

    def save(self) -> None:
        try:
            self.organizer.save(
                self.game.id,
                Annotation(
                    self.status.currentText(),
                    self.rating.value(),
                    self.notes.toPlainText(),
                    tuple(tag.strip() for tag in self.tags.text().split(",") if tag.strip()),
                    tuple(item.text() for item in self.collections.selectedItems()),
                ),
            )
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Organization not saved", str(error))
            return
        self.accept()


class CollectionsDialog(QDialog):
    def __init__(self, organizer: LibraryOrganizer, parent: QWidget | None = None):
        super().__init__(parent)
        self.organizer = organizer
        self.setWindowTitle("Collections & metadata exchange")
        self.resize(640, 540)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Collections link games without copying files. Removing a collection "
            "keeps every game, note, save and play session."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        for label, callback in [
            ("New", self.create_collection),
            ("Rename", self.rename),
            ("Remove", self.remove),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        privacy = QLabel(
            "Export includes notes, tags, ratings, play status, collections and content "
            "hashes. Review private notes before sharing. ROM paths, files, artwork, "
            "saves and session history are excluded."
        )
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        row = QHBoxLayout()
        for label, callback in [
            ("Export organization", self.export),
            ("Import organization", self.import_file),
            ("Done", self.accept),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        self.list.addItems(self.organizer.collections())

    def create_collection(self) -> None:
        text, accepted = QInputDialog.getText(self, "New collection", "Name")
        if accepted:
            try:
                self.organizer.create_collection(text)
                self.refresh()
            except (ValueError, sqlite3.Error) as error:
                QMessageBox.warning(self, "Collection not created", str(error))

    def rename(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        text, accepted = QInputDialog.getText(self, "Rename collection", "Name", text=item.text())
        if accepted:
            try:
                self.organizer.rename_collection(item.text(), text)
                self.refresh()
            except (ValueError, sqlite3.Error) as error:
                QMessageBox.warning(self, "Collection not renamed", str(error))

    def remove(self) -> None:
        item = self.list.currentItem()
        if (
            item
            and QMessageBox.question(
                self,
                "Remove collection",
                "Remove this collection and its memberships? Games are kept.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.organizer.delete_collection(item.text())
            self.refresh()

    def export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export organization", "forge-organization.json", "JSON (*.json)"
        )
        if filename:
            try:
                count = self.organizer.export(Path(filename))
                QMessageBox.information(self, "Export complete", f"Exported {count} games.")
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Export failed", str(error))

    def import_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Import organization", "", "JSON (*.json)")
        if not filename:
            return
        try:
            preview = self.organizer.read_import(Path(filename))
            count = len(preview["matches"])
            if (
                QMessageBox.question(
                    self,
                    "Review metadata import",
                    f"Replace organization for {count} matching games and merge "
                    f"{len(preview['collections'])} collection names? "
                    f"{preview['unknown']} unknown games will be skipped. "
                    "Notes, tags, status, ratings and memberships "
                    "for matching games will be replaced. "
                    "Other library data stays unchanged.",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            recovery = self.organizer.database.path.parent / "backups"
            recovery.mkdir(parents=True, exist_ok=True)
            backup = recovery / (
                "organization-before-import-"
                + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
                + ".json"
            )
            self.organizer.export(backup)
            self.organizer.apply_import(preview)
            self.refresh()
            QMessageBox.information(
                self,
                "Import complete",
                f"Updated {count} matching games. Recovery metadata saved to:\n{backup}",
            )
        except (OSError, ValueError, TypeError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Import failed", str(error))


class HistoryDialog(QDialog):
    def __init__(
        self, organizer: LibraryOrganizer, game: Game | None = None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Play history" + (" · " + game.display_title if game else ""))
        self.resize(780, 560)
        layout = QVBoxLayout(self)
        records = organizer.history(game.id if game else None)
        layout.addWidget(
            QLabel(f"{len(records)} most recent sessions · timestamps include timezone")
        )
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "\n\n".join(
                f"{r['title']} · {r['system_id']}\n{r['started_at']} → {r['ended_at']}\n"
                f"{r['duration_seconds']} seconds · {r['exit_reason']} · "
                f"{r['core_filename']} {r['core_version'] or ''}"
                for r in records
            )
            or "No play sessions yet. Completed runtime sessions appear here."
        )
        layout.addWidget(text, 1)
        close = QPushButton("Done")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
