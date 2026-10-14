"""Helpers every reader shares: build a job in the common format, parse dates, strip HTML."""
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .. import places

SOURCE_TYPE = {"A": "Feed", "B": "Platform", "C": "Custom page"}


def parse_date(v) -> date | None:
    """ISO string, RFC 822 (RSS), epoch seconds or milliseconds, or a date; None when it cannot be read."""
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
        n = float(v)
        n = n / 1000 if n > 1e11 else n
        return datetime.fromtimestamp(n, tz=timezone.utc).date()
    s = str(v).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(s).date()
    except (TypeError, ValueError):
        return None


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def make_job(src: dict, title: str, url: str, *, location: str = "", more: str = "", remote: bool = False, company: str | None = None,
             posted=None, job_id=None, skills="", salary: str = "", work_mode: str = "", job_type: str = "", experience: str = "") -> dict | None:
    """One job in the common format (the V2 fields plus source, job_id, tier and eligibility). None when title or link is missing."""
    title, url = (title or "").strip(), (url or "").strip()
    if not title or not url:
        return None
    if isinstance(skills, (list, tuple)):
        skills = ", ".join(str(s) for s in skills if s)
    c = places.classify(location, more, remote)
    if not work_mode:
        work_mode = "Remote" if c["remote"] else ""
    return {
        "site": src["name"], "source_id": src["id"], "source_type": SOURCE_TYPE.get(src.get("cls", ""), src.get("cls", "")),
        "job_id": str(job_id if job_id not in (None, "") else url), "title": title, "company": (company or src.get("company") or src["name"]).strip(),
        "location": (location or "").strip(), "more_locations": (more or "").strip(), "experience": experience, "salary": salary,
        "work_mode": work_mode, "skills": skills, "posted_date": parse_date(posted), "first_seen": None, "role_hint": "", "job_type": job_type,
        "url": url, **c,
    }


def days_ago(text: str, today: date | None = None) -> date | None:
    """'Posted Today', 'Posted 5 Days Ago', 'Posted 30+ Days Ago' (Workday)."""
    today = today or date.today()
    t = (text or "").lower()
    if "today" in t:
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day", t)
    return today - timedelta(days=int(m.group(1))) if m else None
