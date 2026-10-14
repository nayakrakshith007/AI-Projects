"""Turn Wellfound role-page HTML into plain job dicts. Pure functions: no browser, easy to test with saved HTML."""
import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from common.geo import is_indian_place

from . import config

BASE = config.BASE
_REL = re.compile(r"(?:(\d+)|an?|one)\s*(minute|hour|day|week|month|year)s?\s+ago", re.I)
_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}
_EXP = re.compile(r"(\d+)\s*years?\s*of\s*exp", re.I)
_EXTRA_LOCATIONS = re.compile(r"\s*\+\s*(\d+)\s*$")
_MONEY = re.compile(r"[₹$€£]|equity|%")
_MODES = ("Onsite or remote", "In office", "Remote only", "Remote", "Hybrid")
_WORLDWIDE = re.compile(r"anywhere|worldwide|global|everywhere|any location|all locations", re.I)
KEEP_LOCATIONS = ("India", "Remote - India", "Remote - anywhere", "Remote - location not stated")


def posted_to_date(text: str, today: date | None = None) -> date | None:
    """'6 days ago' -> six days back, '3 weeks ago' -> 21 days back, '1 month ago' -> 30 days back; unknown -> None.
    Wellfound only gives a coarse label, so the date is an estimate."""
    today = today or date.today()
    t = (text or "").lower()
    if re.search(r"\b(today|just now)\b", t):
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)
    m = _REL.search(t)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    return today - timedelta(days=n * _DAYS[m.group(2).lower()])


def classify_location(location: str, work_mode: str, kind: str) -> str:
    """Where a job can be done from, for the India filter.

    India / Remote - India: the place is Indian. Remote - anywhere: the place says worldwide. Remote - location not stated:
    a remote-list job with no place at all. Anything else is "Outside India: <place>" and is dropped by default.
    A job on the India list is India even when its place text is odd."""
    loc = (location or "").strip()
    mode = (work_mode or "").lower()
    if is_indian_place(loc):
        return "Remote - India" if mode.startswith("remote") else "India"
    if _WORLDWIDE.search(loc):
        return "Remote - anywhere"
    if kind == "india":
        return "India"
    if not loc:
        return "Remote - location not stated"
    return f"Outside India: {loc}"


_PAGE_OF = re.compile(r"Page\s+\d+\s+of\s+(\d+)", re.I)


def total_pages(page_html: str) -> int | None:
    """Number of pages a list has, from the 'Page 1 of 24' text on the page; None when the page does not say."""
    text = BeautifulSoup(page_html, "html.parser").get_text(" ", strip=True)
    m = _PAGE_OF.search(text)
    return int(m.group(1)) if m else None


def page_title(page_html: str) -> str:
    soup = BeautifulSoup(page_html, "html.parser")
    return soup.title.get_text(strip=True) if soup.title else ""


def is_generic_page(title: str, slug: str) -> bool:
    """Wellfound answers an unknown role name with its generic 'India Jobs' page (thousands of unrelated jobs).
    A real role page has the role's words in its title."""
    t = (title or "").lower()
    words = [w for w in slug.split("-") if w]
    return not words or not all(w in t for w in words)


def _text(node, selector: str) -> str:
    el = node.select_one(selector)
    return el.get_text(" ", strip=True) if el else ""


def _cards(soup: BeautifulSoup) -> list:
    cards = [d for d in soup.find_all("div") if all(c in (d.get("class") or []) for c in config.CARD_CLASSES) and d.select_one(config.JOB_LINK)]
    if cards:
        return cards
    found = []                                   # fallback if the class names change: climb from each company header
    for header in soup.select("[data-testid='startup-header']"):
        node = header
        while node.parent is not None and not node.select_one(config.JOB_LINK):
            node = node.parent
        if node not in found:
            found.append(node)
    return found


def _company(card) -> dict:
    header = card.select_one("[data-testid='startup-header']") or card
    link = header.select_one("a[href*='/company/']")
    return {
        "company": _text(header, "h2"),
        "company_page": BASE + link["href"].split("?")[0] if link and link.get("href") else "",
        "company_about": _text(header, "span.text-xs.text-neutral-1000"),
        "company_size": _text(header, "span.italic").replace(" Employees", "").strip(),
        "company_tags": ", ".join(x.get_text(" ", strip=True) for x in card.select("li div.line-clamp-1")),
        "actively_hiring": "Yes" if "Actively Hiring" in header.get_text(" ", strip=True) else "",
    }


def _job(row_link, company: dict, today: date | None) -> dict:
    row = row_link.parent.parent.parent
    salary = equity = mode = location = exp = ""
    extra = 0
    for span in row.select("span.pl-1.text-xs"):
        text = span.get_text(" ", strip=True)
        m = _EXP.search(text)
        if m:
            exp = f"{m.group(1)}+ years"
        elif _MONEY.search(text):
            salary, _, equity = (p.strip() for p in text.partition("•"))
            if "equity" in salary.lower() or "%" in salary:      # only equity was shown
                salary, equity = "", salary
        else:
            head, _, tail = text.partition("•")
            if head.strip() in _MODES:
                mode, location = head.strip(), tail.strip()
            else:
                location = text
            more = _EXTRA_LOCATIONS.search(location)
            if more:
                extra = int(more.group(1))
                location = location[: more.start()].strip()
    posted = _text(row, "span.text-dark-a")
    kind = _text(row, "span.whitespace-nowrap")
    return {
        "title": row_link.get_text(" ", strip=True), "url": BASE + row_link["href"].split("?")[0],
        "job_type": kind, "salary": salary, "equity": equity, "work_mode": mode, "location": location,
        "more_locations": extra or "", "experience": exp,
        "posted_text": posted, "posted_date": posted_to_date(posted, today), **company,
    }


def parse_page(page_html: str, today: date | None = None) -> list[dict]:
    """Every job on a role page, with its company details."""
    soup = BeautifulSoup(page_html, "html.parser")
    jobs = []
    for card in _cards(soup):
        company = _company(card)
        for link in card.select(config.JOB_LINK):
            if link.get("href") and re.search(r"/jobs/\d+", link["href"]):
                jobs.append(_job(link, company, today))
    return jobs
