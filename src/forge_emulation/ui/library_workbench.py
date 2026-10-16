from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..library_tools import LibraryTools
from ..models import Game
from ..organization import STATUSES, Annotation


class LibraryWorkbench(QDialog):
    def __init__(self, tools: LibraryTools, games: list[Game], parent: QWidget | None = None):
        super().__init__(parent)
        self.tools, self.games = tools, games
        self.setWindowTitle("Library workbench · bulk organization")
        self.resize(1040, 720)
        layout = QVBoxLayout(self)
        note = QLabel(
            "This table starts with the current library view. Select rows with Ctrl/Shift. "
            "Bulk changes preserve personal notes, existing tags and memberships."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(len(games), 6)
        self.table.setHorizontalHeaderLabels(
            ["Title", "System", "Play status", "Rating", "Playtime (min)", "Tags"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        self.status = QComboBox()
        self.status.addItems(["Keep play status", *STATUSES])
        self.rating = QComboBox()
        self.rating.addItem("Keep rating", None)
        for rating in range(6):
            self.rating.addItem("Unrated" if rating == 0 else f"{rating} stars", rating)
        self.favorite = QComboBox()
        self.favorite.addItem("Keep favorites", None)
        self.favorite.addItem("Add to favorites", True)
        self.favorite.addItem("Remove favorites", False)
        row = QHBoxLayout()
        for widget in (self.status, self.rating, self.favorite):
            row.addWidget(widget)
        layout.addLayout(row)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("Add tags (comma separated)")
        self.collection = QComboBox()
        self.collection.addItem("Keep collections", None)
        for name in tools.organizer.collections():
            self.collection.addItem("Add to " + name, name)
        row = QHBoxLayout()
        row.addWidget(self.tags, 1)
        row.addWidget(self.collection, 1)
        apply = QPushButton("Apply to selected games")
        apply.setObjectName("Primary")
        apply.clicked.connect(self.apply)
        row.addWidget(apply)
        layout.addLayout(row)
        self.include_notes = QCheckBox("Include private notes in CSV")
        layout.addWidget(self.include_notes)
        actions = QHBoxLayout()
        for text, callback in [
            ("Select all", self.table.selectAll),
            ("Export selected / visible CSV", self.export),
            ("Done", self.accept),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.refresh()

    def refresh(self) -> None:
        values = self.tools.organizer.all_annotations()
        for row, game in enumerate(self.games):
            value = values.get(game.id, Annotation())
            for column, text in enumerate(
                [
                    game.display_title,
                    game.system_id,
                    value.status,
                    str(value.rating),
                    str(game.playtime_seconds // 60),
                    ", ".join(value.tags),
                ]
            ):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def selected(self) -> list[Game]:
        return [self.games[index.row()] for index in self.table.selectionModel().selectedRows()]

    def apply(self) -> None:
        games = self.selected()
        if not games:
            QMessageBox.information(self, "Select games", "Select one or more table rows first.")
            return
        if QMessageBox.question(
            self, "Review bulk organization", f"Apply the selected changes to {len(games)} games?"
        ) != (QMessageBox.StandardButton.Yes):
            return
        try:
            self.tools.bulk_update(
                [g.id for g in games],
                status=self.status.currentText() if self.status.currentIndex() else None,
                rating=self.rating.currentData(),
                favorite=self.favorite.currentData(),
                add_tags=tuple(t.strip() for t in self.tags.text().split(",") if t.strip()),
                collection=self.collection.currentData(),
            )
            self.refresh()
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Bulk changes not applied", str(error))

    def export(self) -> None:
        games = self.selected() or self.games
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export visible library data", "forge-library.csv", "CSV (*.csv)"
        )
        if filename:
            try:
                self.tools.export_csv(
                    games, Path(filename), include_notes=self.include_notes.isChecked()
                )
                QMessageBox.information(
                    self,
                    "CSV exported",
                    f"Exported {len(games)} games. ROM paths/files are excluded.",
                )
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Export failed", str(error))
