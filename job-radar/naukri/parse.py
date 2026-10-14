"""Turn Naukri result-card HTML into plain dicts. Pure functions: no browser, easy to test with saved HTML."""
import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

_REL = re.compile(r"(?:(\d+)|an?|one)\s*(minute|min|hour|hr|day|week|month|year)s?\s+ago", re.I)
_DAYS = {"minute": 0, "min": 0, "hour": 0, "hr": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def posted_to_date(text: str, today: date | None = None) -> date | None:
    """'1 day ago' -> yesterday, 'Few hours ago' / 'Just now' -> today, unknown -> None."""
    today = today or date.today()
    t = (text or "").lower()
    if re.search(r"\b(today|just now|few (?:minutes|hours))\b", t):
        return today
    m = _REL.search(t)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    return today - timedelta(days=n * _DAYS[m.group(2).lower()])


def _text(node, selector: str) -> str:
    el = node.select_one(selector)
    return el.get_text(" ", strip=True) if el else ""


def parse_card(html: str, today: date | None = None) -> dict | None:
    """Parse one job card. Returns None when the card has no title link."""
    soup = BeautifulSoup(html, "html.parser")
    a = soup.select_one("a.title")
    if not a or not a.get("href"):
        return None
    loc, exp = soup.select_one(".locWdth"), soup.select_one(".expwdth")
    posted_text = _text(soup, ".job-post-day")
    return {
        "title": a.get("title") or a.get_text(strip=True),
        "company": _text(soup, "a.comp-name"),
        "experience": exp.get_text(strip=True) if exp else "",
        "location": (loc.get("title") or loc.get_text()).strip() if loc else "",
        "snippet": _text(soup, ".job-desc"),
        "skills": ", ".join(li.get_text(strip=True) for li in soup.select("li.tag-li")),
        "posted_text": posted_text,
        "posted_date": posted_to_date(posted_text, today),
        "url": a["href"].split("?")[0],
    }


def parse_page(page_html: str, today: date | None = None) -> list[dict]:
    """Parse every card on a results page."""
    soup = BeautifulSoup(page_html, "html.parser")
    jobs = [parse_card(str(c), today) for c in soup.select("div.srp-jobtuple-wrapper")]
    return [j for j in jobs if j]
