"""The list of sources (radar3/data/sources.csv) and which of them are due in a run."""
import csv
from datetime import date

from . import config

WEEKLY_EVERY_DAYS = 7


def load_sources(path=config.SOURCES_CSV) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def enabled(sources: list[dict]) -> list[dict]:
    return [s for s in sources if s.get("enabled") == "yes"]


def select(sources: list[dict], mode: str = "auto", stats: dict | None = None, today: date | None = None, only: list[str] | None = None) -> list[dict]:
    """The enabled sources to read now.
    only: exactly these ids. 'all': every enabled source. 'daily': the daily ones. 'auto': the daily ones plus any weekly one whose last good read
    is 7 or more days old (or never happened), so a missed week is caught up."""
    rows = enabled(sources)
    if only:
        wanted = set(only)
        return [s for s in rows if s["id"] in wanted]
    if mode == "all":
        return rows
    stats, today = stats or {}, today or date.today()
    chosen = []
    for s in rows:
        if s["schedule"] == "daily":
            chosen.append(s)
        elif mode == "auto":
            last = (stats.get(s["id"]) or {}).get("last_ok")
            if not last or (today - date.fromisoformat(last)).days >= WEEKLY_EVERY_DAYS:
                chosen.append(s)
    return chosen


def coverage(sources: list[dict]) -> dict:
    """Counts for the progress page: every row has exactly one state."""
    out = {"working": 0, "candidate": 0, "parked": 0, "skipped": 0, "duplicate": 0}
    for s in sources:
        if s["cls"] == "X":
            out["duplicate"] += 1
        elif s["cls"] == "S":
            out["skipped"] += 1
        elif s["cls"] == "D":
            out["parked"] += 1
        elif s["enabled"] == "yes":
            out["working"] += 1
        else:
            out["candidate"] += 1
    return out
