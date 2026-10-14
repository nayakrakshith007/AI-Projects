"""Turn LinkedIn public search-card HTML into plain dicts. Pure functions: no browser, easy to test."""
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

_REL = re.compile(r"(?:(\d+)|an?|one)\s*(minute|hour|day|week|month|year)s?\s+ago", re.I)
_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def posted_to_date(text: str, today: date | None = None) -> date | None:
    """'7 hours ago' -> today, '2 days ago' -> two days back, unknown -> None."""
    today = today or date.today()
    t = (text or "").lower()
    if re.search(r"\b(today|just now)\b", t):
        return today
    m = _REL.search(t)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    return today - timedelta(days=n * _DAYS[m.group(2).lower()])


def _text(node, selector: str) -> str:
    el = node.select_one(selector)
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse_card(html: str, today: date | None = None) -> dict | None:
    """Parse one search card. Returns None when it has no job link."""
    soup = BeautifulSoup(html, "html.parser")
    a = soup.select_one("a.base-card__full-link")
    if not a or not a.get("href"):
        return None
    time_el = soup.select_one("time")
    posted_text = time_el.get_text(strip=True) if time_el else ""
    posted = None
    if time_el and time_el.get("datetime"):
        try:
            posted = datetime.strptime(time_el["datetime"][:10], "%Y-%m-%d").date()
        except ValueError:
            posted = None
    if posted is None:
        posted = posted_to_date(posted_text, today)
    return {
        "title": _text(soup, "h3.base-search-card__title"),
        "company": _text(soup, "h4.base-search-card__subtitle"),
        "location": _text(soup, "span.job-search-card__location"),
        "posted_text": posted_text,
        "posted_date": posted,
        "url": a["href"].split("?")[0],
    }


def parse_page(page_html: str, today: date | None = None) -> list[dict]:
    """Parse every card on a results page."""
    soup = BeautifulSoup(page_html, "html.parser")
    jobs = [parse_card(str(c), today) for c in soup.select("div.base-search-card")]
    return [j for j in jobs if j]
