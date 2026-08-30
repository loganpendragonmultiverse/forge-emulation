from __future__ import annotations

import shutil
from pathlib import Path

SIGNATURES = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
    ".bmp": (b"BM",),
}


def install_artwork(source: Path, artwork_dir: Path, game_id: str) -> Path:
    extension = source.suffix.lower()
    if extension not in SIGNATURES or not source.is_file():
        raise ValueError("Choose a PNG, JPEG, WebP, or BMP image.")
    if source.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Artwork must be 20 MiB or smaller.")
    header = source.read_bytes()[:12]
    if not any(header.startswith(signature) for signature in SIGNATURES[extension]):
        raise ValueError("The selected file does not appear to be a valid image.")
    if extension == ".webp" and header[8:12] != b"WEBP":
        raise ValueError("The selected file does not appear to be a valid WebP image.")
    artwork_dir.mkdir(parents=True, exist_ok=True)
    for existing in artwork_dir.glob(f"{game_id}.*"):
        existing.unlink(missing_ok=True)
    target = artwork_dir / f"{game_id}{extension}"
    shutil.copy2(source, target)
    return target
