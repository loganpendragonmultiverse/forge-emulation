from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..database import LibraryDatabase
from ..launch import GameLauncher, LaunchError
from ..models import Game, GameCandidate
from ..paths import AppPaths
from ..scanner import scan_paths
from ..systems import SYSTEM_BY_ID, SYSTEMS

APP_STYLE = """
QMainWindow, QWidget#Root { background: #090b10; color: #f2f4f8; }
QWidget { font-family: "Segoe UI"; font-size: 14px; }
QFrame#Sidebar { background: #0e1118; border-right: 1px solid #202632; }
QLabel#Brand { font-size: 22px; font-weight: 700; color: #ffffff; }
QLabel#BrandMark { background: #f05a47; border-radius: 9px; color: white; font-weight: 800; }
QLabel#Eyebrow { color: #f47a67; font-size: 12px; font-weight: 700; }
QLabel#Title { color: #ffffff; font-size: 32px; font-weight: 700; }
QLabel#Muted { color: #8d96a8; }
QLabel#Metric { color: #ffffff; font-size: 24px; font-weight: 700; }
QLabel#CardTitle { color: #ffffff; font-size: 16px; font-weight: 650; }
QLabel#SystemChip {
    padding: 4px 8px;
    border-radius: 7px;
    color: #dfe6f3;
    background: #242a36;
    font-size: 11px;
    font-weight: 700;
}
QPushButton { border: 0; border-radius: 9px; padding: 10px 14px; color: #d5dae4; text-align: left; }
QPushButton:hover { background: #1b202b; color: #ffffff; }
QPushButton[nav="true"]:checked { background: #252b38; color: #ffffff; font-weight: 650; }
QPushButton#Primary { background: #f05a47; color: #ffffff; font-weight: 700; text-align: center; }
QPushButton#Primary:hover { background: #ff6c58; }
QPushButton#Secondary { background: #202632; color: #ffffff; font-weight: 650; text-align: center; }
QPushButton#Secondary:hover { background: #2a3240; }
QPushButton#Favorite {
    background: transparent;
    color: #a8b0be;
    padding: 5px;
    font-size: 18px;
    text-align: center;
}
QPushButton#Favorite:checked { color: #f5c451; }
QLineEdit {
    background: #141821;
    border: 1px solid #272e3a;
    border-radius: 10px;
    padding: 10px 13px;
    color: white;
    selection-background-color: #f05a47;
}
QLineEdit:focus { border-color: #535f73; }
QFrame#MetricCard, QFrame#GameCard, QFrame#EmptyCard {
    background: #11151d;
    border: 1px solid #202632;
    border-radius: 13px;
}
QFrame#SystemInfo, QFrame#DocumentationCard {
    background: #11151d;
    border: 1px solid #202632;
    border-radius: 13px;
}
QLabel#InfoValue { color: #ffffff; font-size: 15px; font-weight: 650; }
QFrame#GameCard:hover { border-color: #3a4353; background: #141923; }
QFrame#Artwork { background: #191e28; border: 0; border-radius: 9px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #343c4b; min-height: 32px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { color: #b7bfcc; spacing: 8px; }
QToolTip { background: #222936; color: white; border: 1px solid #404a5c; padding: 6px; }
"""


def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


class ScanSignals(QObject):
    completed = Signal(list, list)
    progress = Signal(str)
    failed = Signal(str)


class ScanTask(QRunnable):
    def __init__(self, paths: list[Path]):
        super().__init__()
        self.paths = paths
        self.signals = ScanSignals()

    def run(self) -> None:
        try:
            games, errors = scan_paths(
                self.paths,
                progress=lambda path: self.signals.progress.emit(path.name),
            )
            self.signals.completed.emit(games, errors)
        except Exception as exc:
            logging.exception("Library scan failed")
            self.signals.failed.emit(str(exc))


class GameDetailsDialog(QDialog):
    def __init__(self, game: Game, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{game.title} — ForgeEmulation")
        self.setMinimumWidth(620)
        self.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        system = SYSTEM_BY_ID[game.system_id]
        eyebrow = QLabel(system.name.upper())
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(game.title)
        title.setObjectName("Title")
        title.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)

        fields = (
            ("Emulator backend", "Libretro"),
            ("Emulator core", system.core_name),
            ("Core version", system.core_version),
            ("File", str(game.source_path)),
            ("Archive entry", game.archive_member or "Not archived"),
            ("Detection", game.detection.replace("-", " ").title()),
            ("Size", f"{game.size / 1024:.1f} KiB"),
            ("SHA-256", game.sha256),
            ("SHA-1", game.sha1),
            ("CRC32", game.crc32.upper()),
            ("Playtime", _format_duration(game.playtime_seconds)),
            ("Sessions", str(game.session_count)),
        )
        for label_text, value_text in fields:
            row = QVBoxLayout()
            label = QLabel(label_text.upper())
            label.setObjectName("Muted")
            value = QLabel(value_text)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            row.addWidget(label)
            row.addWidget(value)
            layout.addLayout(row)

        close_button = QPushButton("Close")
        close_button.setObjectName("Secondary")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)


class GameCard(QFrame):
    def __init__(
        self,
        game: Game,
        *,
        play: Any,
        favorite: Any,
        details: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.setObjectName("GameCard")
        self.setMinimumWidth(250)
        self.setMaximumWidth(360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 13, 13, 15)
        layout.setSpacing(11)

        system = SYSTEM_BY_ID[game.system_id]
        artwork = QFrame()
        artwork.setObjectName("Artwork")
        artwork.setMinimumHeight(132)
        artwork.setStyleSheet(
            "QFrame#Artwork {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {system.accent}, "
            "stop:0.45 #202632, stop:1 #11151d); border-radius: 9px;}"
        )
        artwork_layout = QVBoxLayout(artwork)
        artwork_layout.setContentsMargins(16, 14, 16, 14)
        mark = QLabel(system.short_name)
        mark.setStyleSheet("font-size: 31px; font-weight: 800; color: white;")
        mark.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        artwork_layout.addStretch()
        artwork_layout.addWidget(mark)
        layout.addWidget(artwork)

        top = QHBoxLayout()
        chip = QLabel(system.short_name)
        chip.setObjectName("SystemChip")
        top.addWidget(chip)
        top.addStretch()
        star = QPushButton("★")
        star.setObjectName("Favorite")
        star.setCheckable(True)
        star.setChecked(game.favorite)
        star.setFixedSize(34, 32)
        star.setToolTip("Remove from favorites" if game.favorite else "Add to favorites")
        star.clicked.connect(lambda checked: favorite(game, checked))
        top.addWidget(star)
        layout.addLayout(top)

        title = QLabel(game.title)
        title.setObjectName("CardTitle")
        title.setWordWrap(True)
        title.setMinimumHeight(42)
        layout.addWidget(title)

        activity = (
            f"{_format_duration(game.playtime_seconds)} played · {game.session_count} sessions"
            if game.session_count
            else "Ready to play"
        )
        meta = QLabel(activity)
        meta.setObjectName("Muted")
        layout.addWidget(meta)

        actions = QHBoxLayout()
        play_button = QPushButton("Play")
        play_button.setObjectName("Primary")
        play_button.clicked.connect(lambda: play(game))
        details_button = QPushButton("Details")
        details_button.setObjectName("Secondary")
        details_button.clicked.connect(lambda: details(game))
        actions.addWidget(play_button, 2)
        actions.addWidget(details_button, 1)
        layout.addLayout(actions)


class MainWindow(QMainWindow):
    def __init__(self, database: LibraryDatabase, paths: AppPaths):
        super().__init__()
        self.database = database
        self.paths = paths
        self.launcher = GameLauncher(paths)
        self.thread_pool = QThreadPool.globalInstance()
        self.active_process: subprocess.Popen[bytes] | None = None
        self.active_game: Game | None = None
        self.active_result_path: Path | None = None
        self.current_system: str | None = None
        self.favorites_only = False
        self.documentation_open = False
        self._grid_columns = 0
        self.nav_buttons: list[QPushButton] = []
        self.setWindowTitle("ForgeEmulation")
        self.setMinimumSize(1040, 680)
        self.resize(1380, 860)
        self.setAcceptDrops(True)
        self.setStyleSheet(APP_STYLE)
        self._build_ui()
        self._install_shortcuts()
        self.session_timer = QTimer(self)
        self.session_timer.setInterval(500)
        self.session_timer.timeout.connect(self._poll_session)
        self.refresh()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(258)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 24, 20, 22)
        sidebar_layout.setSpacing(7)

        brand_row = QHBoxLayout()
        brand_mark = QLabel("F")
        brand_mark.setObjectName("BrandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(36, 36)
        brand = QLabel("ForgeEmulation")
        brand.setObjectName("Brand")
        brand_row.addWidget(brand_mark)
        brand_row.addWidget(brand)
        brand_row.addStretch()
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addSpacing(26)

        library_label = QLabel("LIBRARY")
        library_label.setObjectName("Muted")
        sidebar_layout.addWidget(library_label)
        self.all_button = self._nav_button("All games", None)
        self.favorite_button = self._nav_button("Favorites", "favorites")
        sidebar_layout.addWidget(self.all_button)
        sidebar_layout.addWidget(self.favorite_button)
        sidebar_layout.addSpacing(20)

        systems_label = QLabel("SYSTEMS")
        systems_label.setObjectName("Muted")
        sidebar_layout.addWidget(systems_label)
        self.system_buttons: dict[str, QPushButton] = {}
        for system in SYSTEMS:
            button = self._nav_button(system.short_name, system.id)
            self.system_buttons[system.id] = button
            sidebar_layout.addWidget(button)
        sidebar_layout.addSpacing(20)
        help_label = QLabel("HELP")
        help_label.setObjectName("Muted")
        sidebar_layout.addWidget(help_label)
        self.documentation_button = self._nav_button("Controls & help", "documentation")
        sidebar_layout.addWidget(self.documentation_button)
        sidebar_layout.addStretch()

        import_button = QPushButton("+  Add game folder")
        import_button.setObjectName("Primary")
        import_button.clicked.connect(self.choose_folder)
        sidebar_layout.addWidget(import_button)
        privacy = QLabel("Local library · No accounts\nNo telemetry · Your files stay put")
        privacy.setObjectName("Muted")
        privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(privacy)
        root_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 25, 32, 20)
        content_layout.setSpacing(19)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("YOUR RETRO LIBRARY")
        eyebrow.setObjectName("Eyebrow")
        self.page_title = QLabel("All games")
        self.page_title.setObjectName("Title")
        self.page_description = QLabel("One library. Four trusted emulator cores.")
        self.page_description.setObjectName("Muted")
        heading.addWidget(eyebrow)
        heading.addWidget(self.page_title)
        heading.addWidget(self.page_description)
        header.addLayout(heading)
        header.addStretch()
        self.header_controls = QWidget()
        controls = QVBoxLayout(self.header_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your library")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(300)
        self.search.textChanged.connect(self.refresh)
        self.fullscreen = QCheckBox("Launch games fullscreen")
        controls.addWidget(self.search)
        controls.addWidget(self.fullscreen)
        header.addWidget(self.header_controls)
        content_layout.addLayout(header)

        self.system_info_card = QFrame()
        self.system_info_card.setObjectName("SystemInfo")
        system_info_layout = QHBoxLayout(self.system_info_card)
        system_info_layout.setContentsMargins(18, 14, 18, 14)
        system_info_layout.setSpacing(30)
        self.system_core_name = self._info_field(system_info_layout, "EMULATOR CORE")
        self.system_core_version = self._info_field(system_info_layout, "VERSION")
        self.system_core_license = self._info_field(system_info_layout, "LICENSE")
        self.system_core_status = self._info_field(system_info_layout, "STATUS")
        content_layout.addWidget(self.system_info_card)
        self.system_info_card.hide()

        self.metrics_widget = QWidget()
        metrics = QHBoxLayout(self.metrics_widget)
        metrics.setContentsMargins(0, 0, 0, 0)
        self.total_metric = self._metric_card("0", "Games")
        self.system_metric = self._metric_card("0", "Systems")
        self.playtime_metric = self._metric_card("0m", "Total playtime")
        self.core_metric = self._metric_card("0 / 4", "Cores ready")
        for card in (
            self.total_metric[0],
            self.system_metric[0],
            self.playtime_metric[0],
            self.core_metric[0],
        ):
            metrics.addWidget(card)
        content_layout.addWidget(self.metrics_widget)

        self.section_widget = QWidget()
        section = QHBoxLayout()
        self.section_widget.setLayout(section)
        section.setContentsMargins(0, 0, 0, 0)
        self.section_title = QLabel("Games")
        self.section_title.setObjectName("CardTitle")
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        section.addWidget(self.section_title)
        section.addStretch()
        section.addWidget(self.status)
        content_layout.addWidget(self.section_widget)

        self.game_scroll = QScrollArea()
        self.game_scroll.setWidgetResizable(True)
        self.game_scroll.setStyleSheet(
            "QScrollArea { border: 0; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self.game_scroll.viewport().setStyleSheet("background: transparent;")
        self.scroll_content = QWidget()
        self.grid = QGridLayout(self.scroll_content)
        self.grid.setContentsMargins(0, 0, 6, 18)
        self.grid.setHorizontalSpacing(15)
        self.grid.setVerticalSpacing(15)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.game_scroll.setWidget(self.scroll_content)
        content_layout.addWidget(self.game_scroll, 1)

        self.documentation_scroll = self._build_documentation()
        self.documentation_scroll.hide()
        content_layout.addWidget(self.documentation_scroll, 1)
        root_layout.addWidget(content, 1)

    @staticmethod
    def _info_field(layout: QHBoxLayout, caption_text: str) -> QLabel:
        field = QVBoxLayout()
        caption = QLabel(caption_text)
        caption.setObjectName("Muted")
        value = QLabel()
        value.setObjectName("InfoValue")
        field.addWidget(caption)
        field.addWidget(value)
        layout.addLayout(field, 1)
        return value

    def _build_documentation(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().setStyleSheet("background: transparent;")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 18)
        layout.setSpacing(14)

        intro = QLabel(
            "ForgeEmulation keeps the library and emulator controls in one place. "
            "Choose a system or game with the mouse, then use the keyboard or a connected "
            "SDL-compatible controller while playing."
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(
            self._documentation_card(
                "Library and mouse",
                (
                    (
                        "Add games",
                        "Click + Add game folder, or drag files and folders into the window.",
                    ),
                    ("Browse", "Choose All games, Favorites, or a system in the sidebar."),
                    ("Search", "Click the search box, or press Ctrl+F, and type part of a title."),
                    ("Play", "Click Play. ForgeEmulation selects the bundled core automatically."),
                    (
                        "Details",
                        "Click Details to view checksums, file information, and the selected core.",
                    ),
                    ("Favorite", "Click the star on a game card."),
                    (
                        "In game",
                        "The mouse does not control gameplay in Version 1; use the "
                        "keyboard or controller.",
                    ),
                ),
            )
        )
        layout.addWidget(
            self._documentation_card(
                "Keyboard controls",
                (
                    ("D-pad", "Arrow keys"),
                    ("B / A", "Z / X"),
                    ("Y / X", "A / S"),
                    ("Select / Start", "Right Shift / Enter"),
                    ("L / R", "Q / W"),
                    ("Pause or resume", "Space"),
                    ("Save / load state", "F5 / F8"),
                    ("Screenshot", "F12"),
                    ("Reset", "Ctrl+R"),
                    ("Fullscreen", "Alt+Enter"),
                    ("Exit game", "Escape"),
                    ("Open this page", "F1"),
                ),
            )
        )
        layout.addWidget(
            self._documentation_card(
                "Controller support",
                (
                    ("Connection", "Connect an SDL-compatible controller before launching a game."),
                    ("Supported layout", "D-pad, four face buttons, Select, Start, L, and R."),
                    (
                        "Common controllers",
                        "Xbox-compatible and many PlayStation, Switch-style, and "
                        "generic SDL controllers.",
                    ),
                    (
                        "Version 1 behavior",
                        "The first recognized controller is used automatically; "
                        "remapping is not included.",
                    ),
                ),
            )
        )
        core_rows = tuple(
            (
                system.name,
                f"{system.core_name} {system.core_version} · {system.core_license}",
            )
            for system in SYSTEMS
        )
        layout.addWidget(self._documentation_card("Systems and emulator cores", core_rows))
        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _documentation_card(title_text: str, rows: tuple[tuple[str, str], ...]) -> QFrame:
        card = QFrame()
        card.setObjectName("DocumentationCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        layout.addWidget(title)
        for label_text, value_text in rows:
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setObjectName("InfoValue")
            label.setMinimumWidth(180)
            value = QLabel(value_text)
            value.setObjectName("Muted")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(label)
            row.addWidget(value, 1)
            layout.addLayout(row)
        return card

    def _metric_card(self, value: str, label: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 13, 17, 13)
        value_label = QLabel(value)
        value_label.setObjectName("Metric")
        caption = QLabel(label)
        caption.setObjectName("Muted")
        layout.addWidget(value_label)
        layout.addWidget(caption)
        return card, value_label

    def _nav_button(self, label: str, target: str | None) -> QPushButton:
        button = QPushButton(label)
        button.setProperty("nav", True)
        button.setCheckable(True)
        button.clicked.connect(
            lambda _checked=False, selected=target: self._select_filter(selected)
        )
        self.nav_buttons.append(button)
        return button

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, self.choose_folder)
        QShortcut(QKeySequence("Ctrl+F"), self, self.search.setFocus)
        QShortcut(QKeySequence("F5"), self, self.refresh)
        QShortcut(QKeySequence("F1"), self, lambda: self._select_filter("documentation"))

    def _select_filter(self, target: str | None) -> None:
        self.documentation_open = target == "documentation"
        self.current_system = target if target in SYSTEM_BY_ID else None
        self.favorites_only = target == "favorites"
        for button in self.nav_buttons:
            button.setChecked(
                button is self.sender()
                or (target == "documentation" and button is self.documentation_button)
            )
        self.refresh()

    def refresh(self) -> None:
        if self.documentation_open:
            self.page_title.setText("Controls & help")
            self.page_description.setText(
                "Keyboard, mouse, controller, and emulator-core reference."
            )
            self.header_controls.hide()
            self.system_info_card.hide()
            self.metrics_widget.hide()
            self.section_widget.hide()
            self.game_scroll.hide()
            self.documentation_scroll.show()
            return
        self.header_controls.show()
        self.metrics_widget.show()
        self.section_widget.show()
        self.game_scroll.show()
        self.documentation_scroll.hide()
        games = self.database.list_games(
            system_id=self.current_system,
            query=self.search.text().strip(),
            favorites_only=self.favorites_only,
        )
        self._clear_layout(self.grid)
        width = max(720, self.game_scroll.viewport().width(), self.width() - 322)
        columns = max(2, min(4, width // 285))
        self._grid_columns = columns
        for index, game in enumerate(games):
            card = GameCard(
                game,
                play=self.play_game,
                favorite=self.toggle_favorite,
                details=self.show_details,
            )
            self.grid.addWidget(card, index // columns, index % columns)
        if not games:
            empty = QFrame()
            empty.setObjectName("EmptyCard")
            empty.setMinimumHeight(210)
            empty_layout = QVBoxLayout(empty)
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title = QLabel("Your library is ready for its first game")
            title.setObjectName("CardTitle")
            body = QLabel(
                "Choose Add game folder or drop a folder here.\n"
                "ForgeEmulation links your files without moving or modifying them."
            )
            body.setObjectName("Muted")
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            add_button = QPushButton("Add game folder")
            add_button.setObjectName("Primary")
            add_button.clicked.connect(self.choose_folder)
            add_button.setMaximumWidth(200)
            center = Qt.AlignmentFlag.AlignCenter
            empty_layout.addWidget(title, 0, center)
            empty_layout.addWidget(body, 0, center)
            empty_layout.addWidget(add_button, 0, center)
            self.grid.addWidget(empty, 0, 0, 1, columns)
        self._refresh_metrics()
        self.section_title.setText(f"{len(games)} game{'s' if len(games) != 1 else ''}")
        if self.favorites_only:
            self.page_title.setText("Favorites")
            self.page_description.setText("The games you want close at hand.")
        elif self.current_system:
            system = SYSTEM_BY_ID[self.current_system]
            self.page_title.setText(system.short_name)
            self.page_description.setText(system.name)
            self.system_core_name.setText(system.core_name)
            self.system_core_version.setText(system.core_version)
            self.system_core_license.setText(system.core_license)
            installed = (self.paths.cores / system.core_filename).is_file()
            self.system_core_status.setText("Ready" if installed else "Missing")
            self.system_info_card.show()
        else:
            self.page_title.setText("All games")
            self.page_description.setText("One library. Four trusted emulator cores.")
            self.system_info_card.hide()

    def _refresh_metrics(self) -> None:
        all_games = self.database.list_games()
        counts = self.database.counts_by_system()
        total_playtime = sum(game.playtime_seconds for game in all_games)
        core_filenames = {system.core_filename for system in SYSTEMS}
        ready_cores = sum((self.paths.cores / filename).is_file() for filename in core_filenames)
        self.total_metric[1].setText(str(len(all_games)))
        self.system_metric[1].setText(str(sum(count > 0 for count in counts.values())))
        self.playtime_metric[1].setText(_format_duration(total_playtime))
        self.core_metric[1].setText(f"{ready_cores} / 4")
        self.all_button.setText(f"All games   {len(all_games)}")
        favorites = sum(game.favorite for game in all_games)
        self.favorite_button.setText(f"Favorites   {favorites}")
        for system in SYSTEMS:
            self.system_buttons[system.id].setText(
                f"{system.short_name}   {counts.get(system.id, 0)}"
            )

    @staticmethod
    def _clear_layout(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                MainWindow._clear_layout(child_layout)

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose a game folder")
        if selected:
            self.scan([Path(selected)])

    def scan(self, paths: list[Path]) -> None:
        self.status.setText("Scanning…")
        task = ScanTask(paths)
        task.signals.progress.connect(lambda name: self.status.setText(f"Scanning {name}"))
        task.signals.completed.connect(self._scan_completed)
        task.signals.failed.connect(self._scan_failed)
        self.thread_pool.start(task)

    def _scan_completed(self, candidates: list[GameCandidate], errors: list[str]) -> None:
        imported, _locations = self.database.import_candidates(candidates)
        self.status.setText(f"Added {imported} new game{'s' if imported != 1 else ''}")
        self.refresh()
        if errors:
            QMessageBox.warning(
                self,
                "Some files could not be scanned",
                "\n".join(errors[:10]),
            )

    def _scan_failed(self, message: str) -> None:
        self.status.setText("Scan failed")
        QMessageBox.critical(self, "Library scan failed", message)

    def toggle_favorite(self, game: Game, favorite: bool) -> None:
        self.database.set_favorite(game.id, favorite)
        self.refresh()

    def show_details(self, game: Game) -> None:
        GameDetailsDialog(game, self).exec()

    def play_game(self, game: Game) -> None:
        if self.active_process and self.active_process.poll() is None:
            QMessageBox.information(self, "Game already running", "Exit the active game first.")
            return
        try:
            command, result_path = self.launcher.prepare(
                game, fullscreen=self.fullscreen.isChecked()
            )
            self.active_process = self.launcher.start(command)
        except (LaunchError, OSError) as exc:
            QMessageBox.critical(self, "Could not launch game", str(exc))
            return
        self.active_game = game
        self.active_result_path = result_path
        self.status.setText(f"Playing {game.title}")
        self.hide()
        self.session_timer.start()

    def _poll_session(self) -> None:
        if not self.active_process or self.active_process.poll() is None:
            return
        self.session_timer.stop()
        game = self.active_game
        result_path = self.active_result_path
        return_code = self.active_process.returncode
        self.active_process = None
        self.active_game = None
        self.active_result_path = None
        self.show()
        self.activateWindow()
        if not game or not result_path:
            return
        try:
            result = self.launcher.read_result(result_path)
            if all(key in result for key in ("started_at", "ended_at", "duration_seconds")):
                duration_value = result["duration_seconds"]
                if not isinstance(duration_value, (str, int, float)):
                    raise TypeError("The runtime returned an invalid duration.")
                system = SYSTEM_BY_ID[game.system_id]
                self.database.record_session(
                    game_id=game.id,
                    started_at=str(result["started_at"]),
                    ended_at=str(result["ended_at"]),
                    duration_seconds=int(duration_value),
                    core_filename=system.core_filename,
                    core_version=str(result.get("core_version") or "") or None,
                    exit_reason=str(result.get("exit_reason") or "unknown"),
                )
            if return_code or result.get("exit_reason") == "error":
                QMessageBox.critical(
                    self,
                    "Runtime stopped",
                    str(result.get("error") or "The emulator runtime stopped unexpectedly."),
                )
        except (LaunchError, OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Session result error", str(exc))
        self.status.setText("Ready")
        self.refresh()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.scan(paths)
            event.acceptProposedAction()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, "grid"):
            columns = max(
                2,
                min(
                    4,
                    max(720, self.game_scroll.viewport().width(), self.width() - 322) // 285,
                ),
            )
            if columns != self._grid_columns:
                self._grid_columns = columns
                QTimer.singleShot(0, self.refresh)

    def closeEvent(self, event: Any) -> None:
        if self.active_process and self.active_process.poll() is None:
            QMessageBox.information(
                self,
                "Game still running",
                "Exit the active game before closing ForgeEmulation.",
            )
            event.ignore()
            return
        event.accept()
