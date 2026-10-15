"""Read-only location preview; absence never updates availability or deletes history."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LocationRecord:
    game_id: str
    title: str
    path: Path
    archive_member: str | None


@dataclass(frozen=True, slots=True)
class LocationFinding:
    location: LocationRecord
    status: str


@dataclass(frozen=True, slots=True)
class LocationReview:
    root: Path
    complete: bool
    findings: tuple[LocationFinding, ...]

    def as_text(self) -> str:
        lines = [
            "Library location review (read-only)",
            str(self.root),
            "Folder scan: " + ("completed" if self.complete else "unavailable or incomplete"),
            "Missing candidate means not seen in this readable folder scan, not proof of deletion.",
            "Container present does not verify a ZIP member or ROM contents.",
            "No library flags, game history, saves, titles or files were changed.",
            "",
        ]
        lines.extend(
            f"{f.status}: {f.location.title} — {f.location.path}"
            + (f" [{f.location.archive_member}]" if f.location.archive_member else "")
            for f in self.findings
        )
        return "\n".join(lines)


def preview_locations(records: Iterable[LocationRecord], root: Path) -> LocationReview:
    selected = root.expanduser().resolve()
    seen: set[Path] = set()
    errors: list[OSError] = []
    complete = False
    try:
        if selected.is_dir():
            for directory, _folders, files in os.walk(
                selected, onerror=errors.append, followlinks=False
            ):
                for name in files:
                    path = Path(directory) / name
                    # Symlinks are outside this preview's evidence boundary.
                    if not path.is_symlink():
                        seen.add(path.resolve())
            complete = not errors and selected.is_dir()
    except OSError:
        complete = False
    findings = []
    for record in sorted(
        records, key=lambda item: (str(item.path), item.archive_member or "", item.game_id)
    ):
        path = record.path.resolve()
        if not path.is_relative_to(selected):
            status = "outside selected folder"
        elif record.path.is_symlink():
            status = "unverified; symlink not followed"
        elif path in seen:
            status = (
                "container present; member unverified"
                if record.archive_member
                else "file present; contents unverified"
            )
        elif complete:
            status = "missing candidate"
        else:
            status = "unverified; folder unavailable or incomplete"
        findings.append(LocationFinding(record, status))
    return LocationReview(selected, complete, tuple(findings))
