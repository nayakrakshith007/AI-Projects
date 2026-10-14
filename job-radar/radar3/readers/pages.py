"""Type B readers for platforms that answer with HTML or a page-builder API: SAP SuccessFactors (classic search pages and the Career Site Builder
JSON) and Avature. One reader per platform; a company is one line in sources.csv. The parsers use the page's own markup, so each has a saved sample test."""
import re
from datetime import datetime
from urllib.parse import quote

from bs4 import BeautifulSoup

from .common import make_job, parse_date
from .keywords import ROLE_KEYWORDS

QUERIES = ROLE_KEYWORDS


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""


# ---------------------------------------------------------------- SuccessFactors, Career Site Builder (JSON)
def sf_csb(src: dict, http) -> list[dict]:
    """SuccessFactors Career Site Builder: POST /services/recruiting/v1/jobs, 10 per page. slug = 'host|location|locale' (location may be empty; locale defaults to en_US, StanChart uses en_GB)."""
    host, _, rest = src["slug"].partition("|")
    location, _, locale = rest.partition("|")
    locale = locale or "en_US"
    jobs, seen = [], set()
    for q in QUERIES:
        for page in range(10):
            _before = len(seen)
            data = http.post_json(f"https://{host}/services/recruiting/v1/jobs", {"locale": locale, "pageNumber": page, "sortBy": "", "keywords": q, "location": location,
                                                                                  "facetFilters": {}, "brand": "", "skills": [], "categoryId": 0, "alertId": "", "rcmCandidateId": ""})
            rows = data.get("jobSearchResult") or []
            for row in rows:
                it = row.get("response") or {}
                jid = it.get("id")
                if jid in seen:
                    continue
                seen.add(jid)
                where = re.sub(r"<br\s*/?>", "", str((it.get("jobLocationShort") or [""])[0] if isinstance(it.get("jobLocationShort"), list) else it.get("jobLocationShort") or ""))
                country = (it.get("jobLocationCountry") or it.get("custCountryRegion") or [""])
                country = country[0] if isinstance(country, list) and country else ""
                if not where and it.get("custprimecity"):
                    where = it["custprimecity"]
                if where and country and country.lower() not in where.lower():
                    where += f", {country}"
                elif not where:
                    where = country
                title = it.get("unifiedStandardTitle") or it.get("urlTitle", "").replace("-", " ")
                j = make_job(src, title, f"https://{host}/job/{it.get('urlTitle')}/{jid}-{locale}", location=where, posted=it.get("unifiedStandardStart"), job_id=jid)
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < 10 or (page + 1) * 10 >= (data.get("totalJobs") or 0):
                break
    return jobs


# ---------------------------------------------------------------- SuccessFactors classic search pages (HTML)
def parse_sf_classic(html: str, host: str, src: dict) -> tuple[list[dict], int]:
    """(jobs, total) from a classic SuccessFactors search page: rows tr.data-row, links a.jobTitle-link, places span.jobLocation."""
    soup = BeautifulSoup(html, "html.parser")
    m = re.search(r"of\s+([\d,]+)", _text(soup.select_one(".paginationLabel")))
    total = int(m.group(1).replace(",", "")) if m else 0
    jobs = []
    for tr in soup.select("tr.data-row"):
        a = tr.select_one("a.jobTitle-link")
        if not a or not a.get("href"):
            continue
        href = a["href"]
        jid = href.rstrip("/").rsplit("/", 1)[-1]
        j = make_job(src, _text(a), f"https://{host}{href}" if href.startswith("/") else href, location=_text(tr.select_one("span.jobLocation")),
                     posted=_text(tr.select_one("span.jobDate")) or None, job_id=jid)
        if j:
            jobs.append(j)
    return jobs, total


def sf_classic(src: dict, http) -> list[dict]:
    """slug = 'host|path', e.g. careers.ey.com|ey. Server-rendered search, 25 per page, filtered to India with locationsearch."""
    host, path = src["slug"].split("|")
    jobs, seen = [], set()
    for q in QUERIES:
        for page in range(8):
            _before = len(seen)
            html = http.get_text(f"https://{host}/{path}/search/?q={quote(q)}&locationsearch=India&startrow={page * 25}")
            rows, total = parse_sf_classic(html, host, src)
            for j in rows:
                if j["job_id"] not in seen:
                    seen.add(j["job_id"])
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < 25 or (page + 1) * 25 >= total:
                break
    return jobs


# ---------------------------------------------------------------- Avature (HTML)
def parse_avature(html: str, src: dict) -> tuple[list[dict], int | None]:
    """(jobs, total) from an Avature SearchJobs page: article.article--result with a JobDetail link and the place in the subtitle."""
    soup = BeautifulSoup(html, "html.parser")
    legend = _text(soup.select_one(".list-controls__text__legend"))
    m = re.search(r"of\s+([\d,]+)", legend)
    total = int(m.group(1).replace(",", "")) if m else None
    jobs = []
    for art in soup.select("article.article--result"):
        a = art.select_one("a[href*='JobDetail']")
        if not a:
            continue
        place = _text(art.select_one(".list-item-location"))
        if not place:                                                   # e.g. Deloitte: 'Deloitte US | Deloitte LLP | Place'
            spans = [_text(s) for s in art.select(".article__header__text__subtitle span") if _text(s)]
            place = spans[-1] if spans else ""
        posted = _text(art.select_one(".list-item-posted"))
        try:
            posted = datetime.strptime(posted, "%d-%b-%Y").date() if posted else None
        except ValueError:
            posted = parse_date(posted)
        ref = _text(art.select_one(".list-item-ref")).replace("Job ID:", "").strip() or a["href"].rstrip("/").rsplit("/", 1)[-1]
        j = make_job(src, _text(a), a["href"], location=re.sub(r"\s+,", ",", place), posted=posted, job_id=ref)
        if j:
            jobs.append(j)
    return jobs, total


def avature(src: dict, http) -> list[dict]:
    """slug = 'host|path|query1,query2', e.g. www.metlifecareers.com|en_US/ml|data,machine learning. The page size varies (6 to 10); the offset follows what came back."""
    host, path, queries = src["slug"].split("|")
    jobs, seen = [], set()
    for q in queries.split(","):
        offset = 0
        for _ in range(12):
            rows, total = parse_avature(http.get_text(f"https://{host}/{path}/SearchJobs/{quote(q.strip())}?jobOffset={offset}"), src)
            new = [j for j in rows if j["job_id"] not in seen]
            for j in new:
                seen.add(j["job_id"])
                if re.match(r"multiple locations?", j["location"], re.I):       # the places are on the job page; the search was for India
                    j.update(tier=4, eligibility="unclear")
                jobs.append(j)
            offset += len(rows)
            if not rows or not new or (total is not None and offset >= total):
                break
    return jobs
