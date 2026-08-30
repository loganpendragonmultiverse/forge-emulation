from __future__ import annotations

import logging
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import pygame
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..artwork import install_artwork
from ..backup import export_backup, restore_backup
from ..controller import (
    GAMEPLAY_ACTIONS,
    LIBRARY_ACTIONS,
    ControllerProfileStore,
    binding_label,
    binding_pressed,
    capture_inputs,
    captured_binding,
)
from ..database import LibraryDatabase
from ..diagnostics import diagnostic_text
from ..launch import GameLauncher, LaunchError
from ..models import Game, GameCandidate
from ..paths import AppPaths
from ..scanner import scan_paths
from ..settings import RuntimeSettings, SettingsStore
from ..systems import SYSTEM_BY_ID, SYSTEMS

APP_STYLE = """
QMainWindow, QDialog, QMessageBox, QWidget#Root {
    background: #090b10;
    color: #f2f4f8;
}
QWidget { font-family: "Segoe UI"; font-size: 14px; color: #f2f4f8; }
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
QComboBox, QSpinBox {
    background: #141821; border: 1px solid #272e3a; border-radius: 9px;
    padding: 9px 12px; color: white; min-height: 22px;
}
QComboBox::drop-down { border: 0; width: 34px; }
QComboBox QAbstractItemView {
    background: #141821;
    border: 1px solid #343c4b;
    color: #ffffff;
    outline: 0;
    padding: 4px;
    selection-background-color: #252b38;
    selection-color: #ffffff;
}
QSpinBox::up-button, QSpinBox::down-button {
    background: #202632;
    border: 0;
    width: 30px;
}
QMessageBox QLabel { color: #f2f4f8; min-width: 300px; }
QMessageBox QPushButton {
    background: #202632;
    border: 1px solid #343c4b;
    color: #ffffff;
    min-width: 116px;
    padding: 9px 12px;
    text-align: center;
}
QMessageBox QPushButton:hover { background: #2a3240; border-color: #566176; }
QMessageBox QPushButton:default { background: #f05a47; border-color: #f05a47; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 2px solid #f47a67;
}
QCheckBox:focus { color: #ffffff; }
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
    def __init__(self, game: Game, edit: Any, settings: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{game.display_title} — ForgeEmulation")
        self.setMinimumWidth(620)
        self.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        system = SYSTEM_BY_ID[game.system_id]
        eyebrow = QLabel(system.name.upper())
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(game.display_title)
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

        actions = QHBoxLayout()
        edit_button = QPushButton("Edit title & artwork")
        edit_button.setObjectName("Secondary")
        edit_button.clicked.connect(lambda: self._edit_and_close(edit, game))
        settings_button = QPushButton("Game settings")
        settings_button.setObjectName("Secondary")
        settings_button.clicked.connect(lambda: settings(game))
        close_button = QPushButton("Close")
        close_button.setObjectName("Secondary")
        close_button.clicked.connect(self.accept)
        actions.addWidget(edit_button)
        actions.addWidget(settings_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)

    def _edit_and_close(self, edit: Any, game: Game) -> None:
        edit(game)
        self.accept()


class SettingsDialog(QDialog):
    def __init__(
        self, store: SettingsStore, game: Game | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.game = game
        self.setWindowTitle("Game settings" if game else "Display & audio settings")
        self.setMinimumWidth(480)
        self.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        title = QLabel("Game override" if game else "Display & audio")
        title.setObjectName("Title")
        layout.addWidget(title)
        self.override = QCheckBox("Use custom settings for this game")
        if game:
            self.override.setChecked(game.id in store.game_overrides)
            layout.addWidget(self.override)
        current = store.for_game(game.id) if game else store.global_settings
        self.fullscreen = QCheckBox("Start fullscreen")
        self.fullscreen.setChecked(current.fullscreen)
        self.scaling = QComboBox()
        self.scaling.addItem("Fit (preserve aspect ratio)", "fit")
        self.scaling.addItem("Integer scaling", "integer")
        self.scaling.addItem("Stretch to window", "stretch")
        self.scaling.setCurrentIndex(max(0, self.scaling.findData(current.scaling)))
        self.filter = QComboBox()
        self.filter.addItem("Nearest (sharp pixels)", "nearest")
        self.filter.addItem("Smooth", "smooth")
        self.filter.setCurrentIndex(max(0, self.filter.findData(current.video_filter)))
        self.volume = QSpinBox()
        self.volume.setRange(0, 100)
        self.volume.setSuffix("%")
        self.volume.setValue(current.volume)
        self.muted = QCheckBox("Mute audio")
        self.muted.setChecked(current.muted)
        self.slot = QSpinBox()
        self.slot.setRange(1, 9)
        self.slot.setValue(current.state_slot)
        for label_text, widget in (
            ("", self.fullscreen),
            ("Scaling", self.scaling),
            ("Video filter", self.filter),
            ("Volume", self.volume),
            ("", self.muted),
            ("Default state slot", self.slot),
        ):
            if label_text:
                label = QLabel(label_text.upper())
                label.setObjectName("Muted")
                layout.addWidget(label)
            layout.addWidget(widget)
        save = QPushButton("Save settings")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        layout.addWidget(save)

    def _values(self) -> RuntimeSettings:
        return RuntimeSettings(
            fullscreen=self.fullscreen.isChecked(),
            scaling=str(self.scaling.currentData()),
            video_filter=str(self.filter.currentData()),
            volume=self.volume.value(),
            muted=self.muted.isChecked(),
            state_slot=self.slot.value(),
        )

    def _save(self) -> None:
        values = self._values()
        if self.game:
            override = {
                "fullscreen": values.fullscreen,
                "scaling": values.scaling,
                "video_filter": values.video_filter,
                "volume": values.volume,
                "muted": values.muted,
                "state_slot": values.state_slot,
            }
            self.store.set_game_override(
                self.game.id, override if self.override.isChecked() else None
            )
        else:
            self.store.set_global(values)
        self.accept()


class MetadataDialog(QDialog):
    def __init__(
        self, game: Game, paths: AppPaths, database: LibraryDatabase, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.game, self.paths, self.database = game, paths, database
        self.artwork_path = game.artwork_path
        self.setWindowTitle("Edit local game information")
        self.setMinimumWidth(520)
        self.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        title = QLabel("Local title & artwork")
        title.setObjectName("Title")
        note = QLabel("Changes stay on this computer and are included in ForgeEmulation backups.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        self.title_edit = QLineEdit(game.custom_title or "")
        self.title_edit.setPlaceholderText(game.title)
        self.artwork_label = QLabel(
            str(game.artwork_path) if game.artwork_path else "No custom artwork"
        )
        self.artwork_label.setObjectName("Muted")
        choose = QPushButton("Choose artwork")
        choose.setObjectName("Secondary")
        choose.clicked.connect(self._choose)
        remove = QPushButton("Remove artwork")
        remove.setObjectName("Secondary")
        remove.clicked.connect(self._remove)
        save = QPushButton("Save local metadata")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addWidget(QLabel("CUSTOM TITLE"))
        layout.addWidget(self.title_edit)
        layout.addWidget(self.artwork_label)
        row = QHBoxLayout()
        row.addWidget(choose)
        row.addWidget(remove)
        layout.addLayout(row)
        layout.addWidget(save)

    def _choose(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Choose game artwork", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not selected:
            return
        try:
            self.artwork_path = install_artwork(Path(selected), self.paths.artwork, self.game.id)
            self.artwork_label.setText(str(self.artwork_path))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Artwork not accepted", str(exc))

    def _remove(self) -> None:
        if self.artwork_path and self.artwork_path.is_relative_to(self.paths.artwork):
            self.artwork_path.unlink(missing_ok=True)
        self.artwork_path = None
        self.artwork_label.setText("No custom artwork")

    def _save(self) -> None:
        self.database.set_metadata(
            self.game.id, custom_title=self.title_edit.text(), artwork_path=self.artwork_path
        )
        self.accept()


class ControllerSettingsDialog(QDialog):
    def __init__(self, store: ControllerProfileStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.joystick: pygame.joystick.JoystickType | None = None
        self.waiting_action: str | None = None
        self.capture_baseline: set[tuple[str, int, str, int]] = set()
        self.mapping_buttons: dict[str, QPushButton] = {}
        self.setWindowTitle("Controller settings — ForgeEmulation")
        self.setMinimumSize(620, 720)
        self.setStyleSheet(APP_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 24, 26, 24)
        outer.setSpacing(14)
        title = QLabel("Controller profiles")
        title.setObjectName("Title")
        description = QLabel(
            "Each connected controller receives its own local profile. Select an action, "
            "then press the button, D-pad direction, or stick direction you want to use."
        )
        description.setObjectName("Muted")
        description.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(description)

        self.controller_select = QComboBox()
        self.controller_select.currentIndexChanged.connect(self._controller_changed)
        outer.addWidget(self.controller_select)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().setStyleSheet("background: transparent;")
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 0, 8, 0)
        rows.setSpacing(8)
        gameplay_heading = QLabel("GAMEPLAY")
        gameplay_heading.setObjectName("Eyebrow")
        rows.addWidget(gameplay_heading)
        for action, label, _retro_id in GAMEPLAY_ACTIONS:
            rows.addLayout(self._mapping_row(action, label))
        library_heading = QLabel("LIBRARY")
        library_heading.setObjectName("Eyebrow")
        rows.addSpacing(8)
        rows.addWidget(library_heading)
        for action, label in LIBRARY_ACTIONS:
            rows.addLayout(self._mapping_row(action, label))
        rows.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        actions = QHBoxLayout()
        reset = QPushButton("Restore defaults")
        reset.setObjectName("Secondary")
        reset.clicked.connect(self._reset)
        close = QPushButton("Done")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        actions.addWidget(reset)
        actions.addStretch()
        actions.addWidget(close)
        outer.addLayout(actions)

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._poll_capture)
        self._refresh_controllers()
        self.timer.start()

    def _mapping_row(self, action: str, label_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setObjectName("InfoValue")
        button = QPushButton("Not assigned")
        button.setObjectName("Secondary")
        button.setMinimumWidth(190)
        button.clicked.connect(
            lambda _checked=False, selected=action: self._begin_capture(selected)
        )
        self.mapping_buttons[action] = button
        row.addWidget(label, 1)
        row.addWidget(button)
        return row

    @staticmethod
    def _pump() -> None:
        with suppress(pygame.error):
            pygame.event.pump()

    def _refresh_controllers(self) -> None:
        current_guid = self.controller_select.currentData()
        self.controller_select.blockSignals(True)
        self.controller_select.clear()
        for index in range(pygame.joystick.get_count()):
            joystick = pygame.joystick.Joystick(index)
            self.controller_select.addItem(joystick.get_name(), joystick.get_guid())
        self.controller_select.blockSignals(False)
        if self.controller_select.count() == 0:
            self.controller_select.addItem("Connect a controller to create a profile", "")
            self.controller_select.setEnabled(False)
            self.joystick = None
        else:
            self.controller_select.setEnabled(True)
            match = self.controller_select.findData(current_guid)
            self.controller_select.setCurrentIndex(max(0, match))
            self._controller_changed(self.controller_select.currentIndex())
        self._refresh_labels()

    def _controller_changed(self, index: int) -> None:
        if index < 0 or not self.controller_select.currentData():
            self.joystick = None
            return
        guid = str(self.controller_select.currentData())
        self.joystick = next(
            (
                pygame.joystick.Joystick(device_index)
                for device_index in range(pygame.joystick.get_count())
                if pygame.joystick.Joystick(device_index).get_guid() == guid
            ),
            None,
        )
        self.waiting_action = None
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        guid = str(self.controller_select.currentData() or "")
        bindings = self.store.bindings_for(guid)
        for action, button in self.mapping_buttons.items():
            button.setEnabled(bool(guid))
            button.setText(binding_label(bindings.get(action)))

    def _begin_capture(self, action: str) -> None:
        if not self.joystick:
            return
        self._pump()
        self.waiting_action = action
        self.capture_baseline = capture_inputs(self.joystick)
        self.mapping_buttons[action].setText("Press a control…")

    def _poll_capture(self) -> None:
        self._pump()
        connected_count = pygame.joystick.get_count()
        visible_count = self.controller_select.count() if self.controller_select.isEnabled() else 0
        if connected_count != visible_count:
            self._refresh_controllers()
            return
        if not self.waiting_action or not self.joystick:
            return
        active = capture_inputs(self.joystick)
        new_inputs = active - self.capture_baseline
        if not new_inputs:
            return
        value = sorted(new_inputs)[0]
        action = self.waiting_action
        self.waiting_action = None
        self.store.set_binding(
            self.joystick.get_guid(),
            self.joystick.get_name(),
            action,
            captured_binding(value),
        )
        self._refresh_labels()

    def _reset(self) -> None:
        if not self.joystick:
            return
        self.store.reset(self.joystick.get_guid(), self.joystick.get_name())
        self.waiting_action = None
        self._refresh_labels()


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
        if game.artwork_path and game.artwork_path.is_file():
            artwork_image = QLabel()
            artwork_image.setMinimumHeight(132)
            artwork_image.setMaximumHeight(132)
            artwork_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            artwork_image.setStyleSheet("background: #191e28; border-radius: 9px;")
            pixmap = QPixmap(str(game.artwork_path))
            artwork_image.setPixmap(
                pixmap.scaled(
                    340,
                    132,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            layout.addWidget(artwork_image)
        else:
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
        star.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        star.clicked.connect(lambda checked: favorite(game, checked))
        top.addWidget(star)
        layout.addLayout(top)

        title = QLabel(game.display_title)
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
        play_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        details_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self.recent_only = False
        self.documentation_open = False
        self.controller_store = ControllerProfileStore.load(paths.controller_profiles)
        self.settings_store = SettingsStore(paths.preferences)
        self.controller_joystick: pygame.joystick.JoystickType | None = None
        self.controller_dialog_open = False
        self._controller_states: dict[str, bool] = {}
        self._controller_repeat_at: dict[str, float] = {}
        self._grid_columns = 0
        self.nav_buttons: list[QPushButton] = []
        self.setWindowTitle("ForgeEmulation")
        self.setMinimumSize(1040, 680)
        self.resize(1380, 860)
        self.setAcceptDrops(True)
        self.setStyleSheet(APP_STYLE)
        self._build_ui()
        self._install_shortcuts()
        self.all_button.setChecked(True)
        self._initialize_controller_navigation()
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

        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.viewport().setStyleSheet("background: transparent;")
        nav_content = QWidget()
        nav_layout = QVBoxLayout(nav_content)
        nav_layout.setContentsMargins(0, 0, 4, 0)
        nav_layout.setSpacing(5)

        library_label = QLabel("LIBRARY")
        library_label.setObjectName("Muted")
        nav_layout.addWidget(library_label)
        self.all_button = self._nav_button("All games", None)
        self.recent_button = self._nav_button("Continue playing", "recent")
        self.favorite_button = self._nav_button("Favorites", "favorites")
        nav_layout.addWidget(self.all_button)
        nav_layout.addWidget(self.recent_button)
        nav_layout.addWidget(self.favorite_button)
        nav_layout.addSpacing(14)

        systems_label = QLabel("SYSTEMS")
        systems_label.setObjectName("Muted")
        nav_layout.addWidget(systems_label)
        self.system_buttons: dict[str, QPushButton] = {}
        for system in SYSTEMS:
            button = self._nav_button(system.short_name, system.id)
            self.system_buttons[system.id] = button
            nav_layout.addWidget(button)
        nav_layout.addSpacing(14)
        help_label = QLabel("HELP")
        help_label.setObjectName("Muted")
        nav_layout.addWidget(help_label)
        self.documentation_button = self._nav_button("Controls && help", "documentation")
        nav_layout.addWidget(self.documentation_button)
        self.controller_settings_button = QPushButton("Controller settings")
        self.controller_settings_button.setObjectName("Secondary")
        self.controller_settings_button.clicked.connect(self.open_controller_settings)
        nav_layout.addWidget(self.controller_settings_button)
        self.display_settings_button = QPushButton("Display && audio")
        self.display_settings_button.setObjectName("Secondary")
        self.display_settings_button.clicked.connect(self.open_display_settings)
        nav_layout.addWidget(self.display_settings_button)
        self.backup_button = QPushButton("Backup && restore")
        self.backup_button.setObjectName("Secondary")
        self.backup_button.clicked.connect(self.backup_restore)
        nav_layout.addWidget(self.backup_button)
        self.diagnostics_button = QPushButton("Diagnostics")
        self.diagnostics_button.setObjectName("Secondary")
        self.diagnostics_button.clicked.connect(self.show_diagnostics)
        nav_layout.addWidget(self.diagnostics_button)
        nav_layout.addStretch()
        nav_scroll.setWidget(nav_content)
        sidebar_layout.addWidget(nav_scroll, 1)

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
        self.page_description = QLabel("One library. Seven trusted emulator cores.")
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
        self.fullscreen = QCheckBox("Global default: launch fullscreen")
        self.fullscreen.setChecked(self.settings_store.global_settings.fullscreen)
        self.fullscreen.toggled.connect(self._set_fullscreen_default)
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
        self.core_metric = self._metric_card("0 / 7", "Cores ready")
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
            "Choose a system or game with the mouse, keyboard, or a connected "
            "SDL-compatible controller. Controller settings are saved locally per device."
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
                    ("Quick menu", "Escape or Tab"),
                    ("Pause or resume", "Space"),
                    ("Save / load state", "F5 / F8 use the selected slot (1–9)"),
                    ("Screenshot", "F12"),
                    ("Reset", "Ctrl+R"),
                    ("Fullscreen", "Alt+Enter"),
                    ("Exit game", "Quick menu → Exit game"),
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
                        "Runtime behavior",
                        "The first recognized controller is used automatically. Open "
                        "Controller settings to remap gameplay and library actions.",
                    ),
                    ("Library navigation", "Use the D-pad, select with A, and go back with B."),
                    ("Quick menu", "Press Select+Start; use D-pad, A to select, B to close."),
                ),
            )
        )
        layout.addWidget(
            self._documentation_card(
                "Local library tools",
                (
                    ("Continue Playing", "Recent sessions, newest first."),
                    (
                        "Display & audio",
                        "Global defaults for scaling, filtering, volume, mute, "
                        "fullscreen, and state slot.",
                    ),
                    ("Per-game settings", "Open Details → Game settings to create an override."),
                    ("Metadata", "Open Details → Edit title & artwork. Files remain local."),
                    (
                        "Backup & restore",
                        "Includes library data, saves, states, screenshots, artwork, "
                        "controller profiles, and preferences—never ROMs.",
                    ),
                    (
                        "Diagnostics",
                        "Copy or save a report that omits ROM paths, titles, "
                        "usernames, and save data.",
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
        button.setProperty("filterTarget", "__all__" if target is None else target)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self.recent_only = target == "recent"
        for button in self.nav_buttons:
            expected = "__all__" if target is None else target
            button.setChecked(button.property("filterTarget") == expected)
        self.refresh()

    def _initialize_controller_navigation(self) -> None:
        pygame.display.init()
        pygame.joystick.init()
        self.controller_timer = QTimer(self)
        self.controller_timer.setInterval(50)
        self.controller_timer.timeout.connect(self._poll_controller_navigation)
        self.controller_timer.start()

    @staticmethod
    def _pump_controller_events() -> None:
        with suppress(pygame.error):
            pygame.event.pump()

    def _connected_controller(self) -> pygame.joystick.JoystickType | None:
        if self.controller_joystick:
            guid = self.controller_joystick.get_guid()
            for index in range(pygame.joystick.get_count()):
                candidate = pygame.joystick.Joystick(index)
                if candidate.get_guid() == guid:
                    self.controller_joystick = candidate
                    return candidate
        if pygame.joystick.get_count():
            self.controller_joystick = pygame.joystick.Joystick(0)
            return self.controller_joystick
        self.controller_joystick = None
        return None

    def _poll_controller_navigation(self) -> None:
        if self.controller_dialog_open or not self.isVisible():
            return
        self._pump_controller_events()
        joystick = self._connected_controller()
        if not joystick:
            self._controller_states.clear()
            return
        bindings = self.controller_store.bindings_for(joystick.get_guid())
        pressed = {
            action: binding_pressed(joystick, bindings[action])
            for action in (
                "up",
                "down",
                "left",
                "right",
                "library_activate",
                "library_back",
            )
        }
        if joystick.get_numaxes() >= 2:
            horizontal = joystick.get_axis(0)
            vertical = joystick.get_axis(1)
            pressed["left"] = pressed["left"] or horizontal <= -0.65
            pressed["right"] = pressed["right"] or horizontal >= 0.65
            pressed["up"] = pressed["up"] or vertical <= -0.65
            pressed["down"] = pressed["down"] or vertical >= 0.65
        now = time.monotonic()
        for direction in ("up", "down", "left", "right"):
            was_pressed = self._controller_states.get(direction, False)
            due = now >= self._controller_repeat_at.get(direction, 0.0)
            if pressed[direction] and (not was_pressed or due):
                self._move_controller_focus(direction)
                self._controller_repeat_at[direction] = now + (0.42 if not was_pressed else 0.12)
        if pressed["library_activate"] and not self._controller_states.get(
            "library_activate", False
        ):
            self._activate_controller_focus()
        if pressed["library_back"] and not self._controller_states.get("library_back", False):
            self._controller_back()
        self._controller_states = pressed

    def _focusable_widgets(self) -> list[QWidget]:
        allowed = (QPushButton, QLineEdit, QCheckBox, QComboBox)
        return [
            widget
            for widget in self.findChildren(QWidget)
            if isinstance(widget, allowed)
            and widget.isVisible()
            and widget.isEnabled()
            and widget.focusPolicy() != Qt.FocusPolicy.NoFocus
        ]

    def _move_controller_focus(self, direction: str) -> None:
        candidates = self._focusable_widgets()
        if not candidates:
            return
        current = QApplication.focusWidget()
        if current not in candidates:
            self.all_button.setFocus(Qt.FocusReason.TabFocusReason)
            return
        origin = current.mapToGlobal(current.rect().center())
        ranked: list[tuple[float, QWidget]] = []
        for candidate in candidates:
            if candidate is current:
                continue
            point = candidate.mapToGlobal(candidate.rect().center())
            dx, dy = point.x() - origin.x(), point.y() - origin.y()
            primary, secondary = (
                (-dy, abs(dx))
                if direction == "up"
                else (dy, abs(dx))
                if direction == "down"
                else (-dx, abs(dy))
                if direction == "left"
                else (dx, abs(dy))
            )
            if primary > 4:
                ranked.append((primary + secondary * 2.2, candidate))
        if ranked:
            ranked.sort(key=lambda item: item[0])
            ranked[0][1].setFocus(Qt.FocusReason.TabFocusReason)

    @staticmethod
    def _activate_controller_focus() -> None:
        widget = QApplication.focusWidget()
        if isinstance(widget, QPushButton):
            widget.click()
        elif isinstance(widget, QCheckBox):
            widget.toggle()
        elif isinstance(widget, QLineEdit):
            widget.setFocus(Qt.FocusReason.TabFocusReason)

    def _controller_back(self) -> None:
        if (
            self.documentation_open
            or self.current_system
            or self.favorites_only
            or self.recent_only
        ):
            self._select_filter(None)
        elif self.search.text():
            self.search.clear()
        else:
            self.all_button.setFocus(Qt.FocusReason.TabFocusReason)

    def open_controller_settings(self) -> None:
        self.controller_dialog_open = True
        try:
            ControllerSettingsDialog(self.controller_store, self).exec()
            self.controller_store = ControllerProfileStore.load(self.paths.controller_profiles)
            self._controller_states.clear()
        finally:
            self.controller_dialog_open = False

    def open_display_settings(self, game: Game | None = None) -> None:
        SettingsDialog(self.settings_store, game, self).exec()
        self.settings_store = SettingsStore(self.paths.preferences)
        self.fullscreen.setChecked(self.settings_store.global_settings.fullscreen)

    def _set_fullscreen_default(self, enabled: bool) -> None:
        current = self.settings_store.global_settings
        self.settings_store.set_global(
            RuntimeSettings(
                fullscreen=enabled,
                scaling=current.scaling,
                video_filter=current.video_filter,
                volume=current.volume,
                muted=current.muted,
                state_slot=current.state_slot,
            )
        )

    def edit_metadata(self, game: Game) -> None:
        MetadataDialog(game, self.paths, self.database, self).exec()
        self.refresh()

    def backup_restore(self) -> None:
        question = QMessageBox(self)
        question.setWindowTitle("Backup & restore")
        question.setText("Export a complete local backup, or restore one?")
        question.setStyleSheet(APP_STYLE)
        export_button = question.addButton("Export backup", QMessageBox.ButtonRole.AcceptRole)
        restore_button = question.addButton("Restore backup", QMessageBox.ButtonRole.ActionRole)
        question.addButton(QMessageBox.StandardButton.Cancel)
        question.exec()
        if question.clickedButton() is export_button:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "Export ForgeEmulation backup",
                str(self.paths.backups / f"ForgeEmulation-backup-{stamp}.zip"),
                "ZIP backup (*.zip)",
            )
            if selected:
                try:
                    manifest = export_backup(self.paths, Path(selected))
                    files = manifest.get("files", [])
                    count = len(files) if isinstance(files, list) else 0
                    QMessageBox.information(
                        self, "Backup complete", f"Saved {count} files to:\n{selected}"
                    )
                except (OSError, ValueError) as exc:
                    QMessageBox.critical(self, "Backup failed", str(exc))
        elif question.clickedButton() is restore_button:
            selected, _ = QFileDialog.getOpenFileName(
                self, "Restore ForgeEmulation backup", str(self.paths.backups), "ZIP backup (*.zip)"
            )
            if (
                selected
                and QMessageBox.question(
                    self,
                    "Restore this backup?",
                    "Current matching files will be replaced. ROM files are never changed.",
                )
                == QMessageBox.StandardButton.Yes
            ):
                try:
                    restore_backup(self.paths, Path(selected))
                    self.database = LibraryDatabase(self.paths.database)
                    self.launcher = GameLauncher(self.paths)
                    self.settings_store = SettingsStore(self.paths.preferences)
                    self.controller_store = ControllerProfileStore.load(
                        self.paths.controller_profiles
                    )
                    self.refresh()
                    QMessageBox.information(
                        self, "Restore complete", "The local backup was restored."
                    )
                except (OSError, ValueError) as exc:
                    QMessageBox.critical(self, "Restore failed", str(exc))

    def show_diagnostics(self) -> None:
        report = diagnostic_text(self.paths, self.database)
        dialog = QDialog(self)
        dialog.setWindowTitle("ForgeEmulation diagnostics")
        dialog.setMinimumSize(720, 620)
        dialog.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(dialog)
        title = QLabel("Copyable diagnostic report")
        title.setObjectName("Title")
        note = QLabel("The report omits ROM paths, game titles, usernames, and save data.")
        note.setObjectName("Muted")
        editor = QPlainTextEdit()
        editor.setPlainText(report)
        editor.setReadOnly(True)
        editor.setMinimumHeight(360)
        copy = QPushButton("Copy report")
        copy.setObjectName("Primary")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(report))
        save = QPushButton("Save report")
        save.setObjectName("Secondary")

        def save_report() -> None:
            selected, _ = QFileDialog.getSaveFileName(
                dialog, "Save diagnostic report", "ForgeEmulation-diagnostics.json", "JSON (*.json)"
            )
            if selected:
                Path(selected).write_text(report, encoding="utf-8")

        save.clicked.connect(save_report)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addWidget(editor)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(save)
        layout.addLayout(row)
        dialog.exec()

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
        games = (
            self.database.recent_games(limit=20, query=self.search.text().strip())
            if self.recent_only
            else self.database.list_games(
                system_id=self.current_system,
                query=self.search.text().strip(),
                favorites_only=self.favorites_only,
            )
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
        elif self.recent_only:
            self.page_title.setText("Continue playing")
            self.page_description.setText("Your most recently played games, newest first.")
            self.system_info_card.hide()
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
            self.page_description.setText("One library. Seven trusted emulator cores.")
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
        self.core_metric[1].setText(f"{ready_cores} / {len(core_filenames)}")
        self.all_button.setText(f"All games   {len(all_games)}")
        favorites = sum(game.favorite for game in all_games)
        self.favorite_button.setText(f"Favorites   {favorites}")
        self.recent_button.setText(
            f"Continue playing   {sum(bool(game.last_played) for game in all_games)}"
        )
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
        GameDetailsDialog(game, self.edit_metadata, self.open_display_settings, self).exec()

    def play_game(self, game: Game) -> None:
        if self.active_process and self.active_process.poll() is None:
            QMessageBox.information(self, "Game already running", "Exit the active game first.")
            return
        try:
            command, result_path = self.launcher.prepare(game)
            self.active_process = self.launcher.start(command)
        except (LaunchError, OSError) as exc:
            QMessageBox.critical(self, "Could not launch game", str(exc))
            return
        self.active_game = game
        self.active_result_path = result_path
        self.status.setText(f"Playing {game.display_title}")
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
                runtime_settings = result.get("runtime_settings")
                if isinstance(runtime_settings, dict):
                    runtime_settings["state_slot"] = result.get("state_slot", 1)
                    self.settings_store.set_game_override(game.id, runtime_settings)
            if return_code or result.get("exit_reason") == "error":
                error = str(result.get("error") or "The emulator runtime stopped unexpectedly.")
                box = QMessageBox(QMessageBox.Icon.Critical, "Runtime stopped", error, parent=self)
                copy_button = box.addButton("Copy diagnostics", QMessageBox.ButtonRole.ActionRole)
                box.addButton(QMessageBox.StandardButton.Close)
                box.exec()
                if box.clickedButton() is copy_button:
                    QApplication.clipboard().setText(diagnostic_text(self.paths, self.database))
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
