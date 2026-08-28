from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))

from generate_test_roms import write_test_roms  # noqa: E402

from forge_emulation.database import LibraryDatabase  # noqa: E402
from forge_emulation.paths import app_paths  # noqa: E402
from forge_emulation.scanner import scan_paths  # noqa: E402
from forge_emulation.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a deterministic frontend smoke image.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="forge-emulation-ui-") as temporary:
        root = Path(temporary)
        roms = root / "roms"
        write_test_roms(roms)
        paths = app_paths(root / "portable")
        for core in (Path(__file__).resolve().parents[1] / "cores").glob("*.dll"):
            (paths.cores / core.name).touch()
        database = LibraryDatabase(paths.database)
        games, errors = scan_paths([roms])
        if errors:
            raise RuntimeError("; ".join(errors))
        database.import_candidates(games)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        for index, game in enumerate(database.list_games()):
            if index in {0, 2}:
                database.set_favorite(game.id, True)
            if index < 3:
                database.record_session(
                    game_id=game.id,
                    started_at=now,
                    ended_at=now,
                    duration_seconds=(index + 1) * 754,
                    core_filename="ui-smoke",
                    core_version="1.0",
                    exit_reason="ui-smoke",
                )
        app = QApplication.instance() or QApplication([])
        if not QFontDatabase.families():
            for filename in ("segoeui.ttf", "seguisb.ttf", "seguisym.ttf"):
                QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / filename))
        window = MainWindow(database, paths)
        window.show()
        app.processEvents()
        app.processEvents()
        if not window.grab().save(str(args.output)):
            raise RuntimeError(f"Could not save {args.output}")
        window.close()
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
