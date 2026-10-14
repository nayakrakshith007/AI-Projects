"""Turn Hirist pages into plain job dicts: tag-page cards (HTML) and search results (the JSON the page loads). Pure functions."""
import math
import re
from datetime import date, datetime, timedelta, timezone

from bs4 import BeautifulSoup

from common.geo import is_bengaluru
from common.inputs import parse_experience

from . import config

BASE = config.BASE
IST = timezone(timedelta(hours=5, minutes=30))
_REL = re.compile(r"(?:(\d+)|an?|one)\s*(minute|hour|day|week|month|year)s?\s+ago", re.I)
_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}
_ID = re.compile(r"-(\d+)(?:\?|$)")
_COUNT = re.compile(r"([\d,]+)\s+Job Vacancies", re.I)


def posted_to_date(text: str, today: date | None = None) -> date | None:
    """'Posted 3 days ago' -> three days back, 'Posted today' -> today, '1 week ago' -> 7 days back; unknown -> None."""
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


def split_title(raw: str, company: str = "") -> tuple[str, str]:
    """Hirist titles read 'Company - Role - Detail'. Returns (company, role title)."""
    raw = (raw or "").strip()
    head, sep, rest = raw.partition(" - ")
    if sep and (not company or company.lower().startswith(head.lower()) or head.lower() in company.lower()):
        return (company or head).strip(), rest.strip()
    return company.strip(), raw


def _exp(lo, hi) -> tuple[int | None, int | None, str]:
    """Experience numbers and text. 0-0 or missing means nothing was stated."""
    lo = None if lo in (None, "") else int(lo)
    hi = None if hi in (None, "") else int(hi)
    if not lo and not hi:
        return None, None, ""
    hi = hi if hi and hi >= (lo or 0) else lo
    return lo, hi, f"{lo or 0}-{hi} years" if hi != lo else f"{lo}+ years"


# ---------------------------------------------------------------- tag pages (HTML cards)
def total_from_title(page_html: str) -> int | None:
    """'887 Job Vacancies' in the page title: how many jobs the list holds."""
    soup = BeautifulSoup(page_html, "html.parser")
    m = _COUNT.search(soup.title.get_text(" ", strip=True) if soup.title else "")
    return int(m.group(1).replace(",", "")) if m else None


def pages_for(total: int | None) -> int | None:
    return math.ceil(total / config.PAGE_SIZE) if total else None


def parse_tag_page(page_html: str, today: date | None = None) -> list[dict]:
    """Every job card on a tag or search page."""
    soup = BeautifulSoup(page_html, "html.parser")
    jobs = []
    for card in soup.select(config.CARD_SELECTOR):
        link = card.select_one("a[href*='/j/']")
        if not link:
            continue
        href = link["href"].split("?")[0]
        m = _ID.search(link["href"])
        text = lambda tid: (card.select_one(f"[data-testid='{tid}']").get_text(" ", strip=True) if card.select_one(f"[data-testid='{tid}']") else "")
        company, title = split_title(text("job_title"))
        exp_text = text("job_experience")
        rng = parse_experience(exp_text)
        lo, hi, shown = _exp(rng[0], rng[1] if rng and rng[1] < 99 else None) if rng else (None, None, "")
        locations = [x.strip() for x in re.split(r"[,/]| \+ ", text("job_location")) if x.strip()]
        posted = text("date_posted")
        jobs.append({
            "id": m.group(1) if m else "", "url": BASE + href, "title": title, "company": company, "designation": "",
            "experience": shown, "experience_min": lo, "experience_max": hi,
            "locations": locations, "location": ", ".join(locations), "bengaluru": "Yes" if is_bengaluru(text("job_location")) else "",
            "work_mode": "", "salary": text("job_salary"),
            "skills": [t.get_text(" ", strip=True) for t in card.select("[data-testid^='job_tag_']")],
            "posted_text": posted.replace("Posted", "").strip(), "posted_date": posted_to_date(posted, today), "posted_at": None,
            "applicants": None, "views": None, "company_rating": None, "company_reviews": None, "source": "tag",
        })
    return jobs


# ---------------------------------------------------------------- search results (JSON the page loads)
def parse_search_json(data: dict) -> list[dict]:
    """Jobs from the JSON a Hirist search page loads for itself. Exact posting time, numeric experience, all locations."""
    jobs = []
    for j in data.get("data") or []:
        url = j.get("jobDetailUrl") or ""
        if not url:
            continue
        company_data = j.get("companyData") or {}
        ab = company_data.get("ambitionBoxInfo") or {}
        company, title = split_title(j.get("title", ""), company_data.get("companyName", ""))
        lo, hi, shown = _exp(j.get("min"), j.get("max"))
        locations = [x["name"] for x in (j.get("locations") or j.get("location") or []) if x.get("name")]
        created = j.get("createdTimeMs")
        posted_at = datetime.fromtimestamp(created / 1000, IST) if created else None
        salary = f"{j['minSal']}-{j['maxSal']} LPA" if not j.get("hideSal") and (j.get("minSal") or j.get("maxSal")) else ""
        jobs.append({
            "id": str(j.get("id", "")), "url": url, "title": title, "company": company, "designation": j.get("jobdesignation") or "",
            "experience": shown, "experience_min": lo, "experience_max": hi,
            "locations": locations, "location": ", ".join(locations), "bengaluru": "Yes" if any(is_bengaluru(x) for x in locations) else "",
            "work_mode": "Work from home" if j.get("workFromHome") else "", "salary": salary,
            "skills": [t["name"] for t in j.get("tags") or [] if t.get("name")],
            "posted_text": "", "posted_date": posted_at.date() if posted_at else None, "posted_at": posted_at.isoformat(timespec="minutes") if posted_at else None,
            "applicants": j.get("applyCount"), "views": j.get("hits"),
            "company_rating": ab.get("aggregateRatingOneDecimal") or j.get("minRatingAb") or None, "company_reviews": ab.get("reviewsCount"),
            "source": "search",
        })
    return jobs


def title_matches(job: dict, keyword: str) -> bool:
    """Does the job look like the keyword? Every word of the keyword appears in the job's title or designation, or the whole
    phrase appears in its skill tags. A rough relevance check, used to compare the two methods, not to drop jobs."""
    words = [w for w in re.split(r"[^a-z0-9+#.]+", keyword.lower()) if len(w) > 1]
    hay = f"{job.get('title', '')} {job.get('designation', '')}".lower()
    if words and all(w in hay for w in words):
        return True
    phrase = keyword.lower()
    return any(phrase in (t or "").lower() for t in job.get("skills", []))
