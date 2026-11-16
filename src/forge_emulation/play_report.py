"""Read-only play statistics from locally recorded sessions."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta

from .database import LibraryDatabase


@dataclass(frozen=True, slots=True)
class PlayTotals:
    label: str
    sessions: int
    seconds: int


@dataclass(frozen=True, slots=True)
class PlayReport:
    games_played: int
    totals: PlayTotals
    by_system: tuple[PlayTotals, ...]
    top_games: tuple[PlayTotals, ...]
    by_day: tuple[PlayTotals, ...]


def play_report(database: LibraryDatabase, end: date, days: int) -> PlayReport:
    """Summarize recorded play by UTC end date, including the selected end date."""
    if type(days) is not int or not 1 <= days <= 366:
        raise ValueError("Choose a report period of 1 to 366 days.")
    start = end - timedelta(days=days - 1)
    stop = end + timedelta(days=1)
    with closing(database.connect()) as connection:
        rows = connection.execute(
            """
            SELECT g.id, COALESCE(NULLIF(g.custom_title, ''), g.title) AS title,
                   g.system_id, date(s.ended_at) AS day,
                   COUNT(*) AS sessions, SUM(s.duration_seconds) AS seconds
            FROM sessions s JOIN games g ON g.id = s.game_id
            WHERE julianday(s.ended_at) >= julianday(?)
              AND julianday(s.ended_at) < julianday(?)
            GROUP BY g.id, day
            """,
            (start.isoformat(), stop.isoformat()),
        )
        titles: dict[str, str] = {}
        games: dict[str, tuple[int, int]] = {}
        systems: dict[str, tuple[int, int]] = {}
        dates: dict[str, tuple[int, int]] = {}
        total_sessions = total_seconds = 0
        for row in rows:
            game_id = str(row["id"])
            titles[game_id] = str(row["title"])
            count, seconds = int(row["sessions"]), int(row["seconds"])
            total_sessions += count
            total_seconds += seconds
            for totals, key in (
                (games, game_id),
                (systems, str(row["system_id"])),
                (dates, str(row["day"])),
            ):
                old_count, old_seconds = totals.get(key, (0, 0))
                totals[key] = old_count + count, old_seconds + seconds

    ranked_games = sorted(
        (PlayTotals(titles[key], *values) for key, values in games.items()),
        key=lambda item: (-item.seconds, -item.sessions, item.label.casefold(), item.label),
    )
    ranked_systems = sorted(
        (PlayTotals(key, *values) for key, values in systems.items()),
        key=lambda item: (-item.seconds, -item.sessions, item.label),
    )
    return PlayReport(
        games_played=len(games),
        totals=PlayTotals("All recorded play", total_sessions, total_seconds),
        by_system=tuple(ranked_systems),
        top_games=tuple(ranked_games[:20]),
        by_day=tuple(PlayTotals(day, *dates[day]) for day in sorted(dates, reverse=True)),
    )
