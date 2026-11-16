"""Keyboard-accessible local play report."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..database import LibraryDatabase
from ..play_report import PlayTotals, play_report
from ..systems import SYSTEM_BY_ID


def _duration(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {seconds:02d}s"


class PlayReportDialog(QDialog):
    def __init__(self, database: LibraryDatabase, parent: QWidget | None = None):
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("Play report")
        self.resize(730, 510)
        layout = QVBoxLayout(self)
        self.period = QComboBox()
        for days in (7, 30, 90, 365):
            self.period.addItem(f"Last {days} days", days)
        self.period.setCurrentIndex(1)
        filters = QFormLayout()
        filters.addRow("&Period", self.period)
        layout.addLayout(filters)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        tabs = QTabWidget()
        self.systems = self.add_table(tabs, "Systems", "System")
        self.games = self.add_table(tabs, "Top games", "Game")
        self.days = self.add_table(tabs, "Daily activity", "Date (UTC)")
        layout.addWidget(tabs, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.period.currentIndexChanged.connect(self.refresh)
        self.refresh()

    @staticmethod
    def add_table(tabs: QTabWidget, title: str, first: str) -> QTableWidget:
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels([first, "Sessions", "Recorded playtime"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setStretchLastSection(True)
        tabs.addTab(table, title)
        return table

    @staticmethod
    def populate(table: QTableWidget, rows: tuple[PlayTotals, ...]) -> None:
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, value in enumerate((row.label, str(row.sessions), _duration(row.seconds))):
                table.setItem(index, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()

    def refresh(self) -> None:
        report = play_report(
            self.database, datetime.now(UTC).date(), int(self.period.currentData())
        )
        self.summary.setText(
            f"{report.games_played} games · {report.totals.sessions} sessions · "
            f"{_duration(report.totals.seconds)} recorded across the selected UTC dates."
            if report.totals.sessions
            else "No recorded sessions in this period."
        )
        systems = tuple(
            PlayTotals(
                SYSTEM_BY_ID[row.label].name if row.label in SYSTEM_BY_ID else row.label,
                row.sessions,
                row.seconds,
            )
            for row in report.by_system
        )
        self.populate(self.systems, systems)
        self.populate(self.games, report.top_games)
        self.populate(self.days, report.by_day)
