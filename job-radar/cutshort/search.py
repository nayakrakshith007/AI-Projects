"""Read the public Cutshort job lists (data science for India, Bengaluru and remote), newest first, one Chrome, a few pages.

A list page shows the newest 50 jobs of its list (Cutshort's own paging does not go further), so a daily run sees every new
job as long as fewer than 50 are posted per list per day. The pages are read from the page's own JSON, not from the screen.
"""
import random
import time
from datetime import datetime, timedelta

from common.inputs import experience_ok

from . import config
from .parse import parse_page
from .session import HumanCheckPending, Session


def _pause(rng: tuple[float, float]) -> None:
    time.sleep(random.uniform(*rng))


def read_list(pg, lst: config.JobList) -> tuple[list[dict], int | None]:
    """Open one list. Returns (jobs, jobs in the whole list). Raises HumanCheckPending when a check is shown."""
    pg.goto(config.list_url(lst.slug), wait_until="domcontentloaded")
    try:
        pg.wait_for_selector("script#__NEXT_DATA__", state="attached", timeout=config.LOAD_TIMEOUT_MS)
    except Exception:
        pass
    _pause(config.PAUSE_AFTER_LOAD)
    html = pg.content()
    jobs, total = parse_page(html)
    if not jobs:
        body = pg.inner_text("body").lower() if pg.query_selector("body") else ""
        if any(m in body for m in config.CHECK_MARKERS):
            raise HumanCheckPending("Cutshort is asking for a human check")
    return jobs, total


def in_window(job: dict, hours: int, now: datetime | None = None) -> bool:
    """Posted inside the window (exact posting time, Indian time)."""
    now = now or datetime.now()
    if not hours or not job.get("posted_at"):
        return True
    return datetime.fromisoformat(job["posted_at"]) >= now - timedelta(hours=hours)


def keep(job: dict, hours: int, min_experience: float, counts: dict, now: datetime | None = None) -> bool:
    """The window, the internship rule and the experience rule. Counts why a job was dropped."""
    if not in_window(job, hours, now):
        counts["outside_window"] += 1
        return False
    if job["job_types"] == ["internship"]:
        counts["dropped_internship"] += 1
        return False
    if not experience_ok(job["experience"], min_experience):
        counts["dropped_experience"] += 1
        return False
    return True


def search(hours: int, min_experience: float, lists: list[config.JobList] | None = None, on_list=None) -> tuple[list[dict], str | None, dict]:
    """Read every list. Returns (jobs, error, stats). A job on several lists is kept once, with every list named."""
    lists = lists or config.load_lists()
    counts = {"outside_window": 0, "dropped_internship": 0, "dropped_experience": 0}
    stats = {"lists": len(lists), "pages": 0, "read": 0, "reports": [], **counts}
    final: dict[str, dict] = {}
    error, session = None, Session()
    try:
        for i, lst in enumerate(lists):
            if i:
                _pause(config.PAUSE_BETWEEN_PAGES)
            try:
                jobs, total = read_list(session.page(), lst)
            except HumanCheckPending as exc:
                error = f"{exc}: double-click check_cutshort.bat"
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:100]} ({lst.slug})"
                session.close()
                session = Session()
                continue
            kept = 0
            stats["pages"] += 1
            stats["read"] += len(jobs)
            for j in jobs:
                if not keep(j, hours, min_experience, counts):
                    continue
                kept += 1
                j["lists"] = [lst.label]
                old = final.get(j["id"])
                if old:
                    old["lists"] = sorted(set(old["lists"]) | {lst.label})
                else:
                    final[j["id"]] = j
            stats["reports"].append({"slug": lst.slug, "label": lst.label, "read": len(jobs), "total": total, "kept": kept,
                                     "oldest": min((j["posted_date"] for j in jobs if j["posted_date"]), default=None)})
            if on_list:
                on_list(lst, len(jobs), total, kept)
            if not jobs:
                stats["reports"][-1]["empty"] = True
                error = error or f"{lst.slug}: no jobs on the page (the list may have been renamed)"
    finally:
        session.close()
    stats.update(counts)
    return list(final.values()), error, stats
