from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Any

_DLL_DIRECTORIES: list[Any] = []


def _prepare_frozen_qt() -> None:
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return
    bundle = Path(sys._MEIPASS)
    pyside = bundle / "PySide6"
    shiboken = bundle / "shiboken6"
    _DLL_DIRECTORIES.extend(
        (os.add_dll_directory(str(pyside)), os.add_dll_directory(str(shiboken)))
    )
    for library in (
        shiboken / "shiboken6.abi3.dll",
        pyside / "Qt6Core.dll",
        pyside / "pyside6.abi3.dll",
        pyside / "Qt6Gui.dll",
        pyside / "Qt6Widgets.dll",
    ):
        ctypes.WinDLL(str(library))


_prepare_frozen_qt()

from forge_emulation.app import main  # noqa: E402

raise SystemExit(main())
