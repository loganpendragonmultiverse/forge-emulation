from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from generate_test_roms import write_test_roms  # noqa: E402


@pytest.fixture
def rom_directory(tmp_path: Path) -> Path:
    destination = tmp_path / "roms"
    write_test_roms(destination)
    return destination
