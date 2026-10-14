"""Turn a Cutshort job-list page into plain job dicts. The page ships its jobs as JSON inside <script id="__NEXT_DATA__">.
Pure functions. The recruiter who posted a job is named in the data; it is not read or kept."""
import json
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from common.geo import is_bengaluru

from . import config

IST = timezone(timedelta(hours=5, minutes=30))
WORK_MODES = {"remote_only": "Remote", "remote_okay": "Onsite or remote", "remote_not_okay": "Onsite"}
JOB_TYPES = {"full_time": "Full time", "part_time": "Part time", "internship": "Internship", "contract": "Contract", "freelance": "Freelance"}


def _next_data(page_html: str) -> dict:
    soup = BeautifulSoup(page_html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    return json.loads(tag.string) if tag and tag.string else {}


def _page_data(page_html: str) -> dict:
    """The jobs block of the list page: {'jobs': [...], 'liveJobCount': N}, or {} if the page has none (no such list, a check)."""
    for q in _next_data(page_html).get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", []):
        key = q.get("queryKey") or []
        if key and key[0] == "jobListData":
            return ((q.get("state") or {}).get("data") or {}).get("data", {}).get("pageData") or {}
    return {}


def html_to_text(fragment: str, limit: int = config.DESCRIPTION_LIMIT) -> str:
    """Job description HTML to plain text: paragraphs on their own lines, list items as '- '."""
    soup = BeautifulSoup(fragment or "", "html.parser")
    for li in soup.find_all("li"):
        li.insert_before("- ")
        li.append("\n")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "ul", "ol"]):
        p.append("\n")
    text = re.sub(r"[ \t]+\n", "\n", soup.get_text())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def posted_ist(iso: str | None) -> datetime | None:
    """'2026-10-07T04:22:39.818Z' (UTC) -> that moment in Indian time, without a zone."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IST).replace(tzinfo=None)
    except ValueError:
        return None


def experience(rng: dict | None) -> tuple[int | None, int | None, str]:
    """(min, max, text). 0 to 0 means nothing was stated (internships, fresher roles)."""
    rng = rng or {}
    lo, hi = rng.get("min"), rng.get("max")
    if not lo and not hi:
        return None, None, ""
    lo = int(lo or 0)
    hi = int(hi) if hi and hi >= lo else lo
    return lo, hi, f"{lo}-{hi} years" if hi != lo else f"{lo}+ years"


def _job(j: dict) -> dict | None:
    url = j.get("publicUrl") or ""
    title = (j.get("headline") or "").strip()
    if not url or not title:
        return None
    fact = j.get("jobFactSummary") or {}
    company = j.get("companyDetails") or {}
    links = company.get("links") or {}
    lo, hi, exp_text = experience(j.get("expRange"))
    posted = posted_ist(fact.get("postedDate"))
    types = j.get("roleTypes") or []
    location = (j.get("locationsText") or fact.get("locations") or "").strip()
    return {
        "id": j.get("_id") or url, "url": url, "title": title,
        "company": (company.get("name") or fact.get("companyName") or "").strip(),
        "hiring_for_client": "Yes" if j.get("hiringForClient") else "",
        "location": location, "bengaluru": "Yes" if is_bengaluru(location) else "",
        "work_mode": WORK_MODES.get(j.get("remoteType") or "", ""),
        "experience": exp_text, "experience_min": lo, "experience_max": hi,
        "job_types": types, "job_type": ", ".join(JOB_TYPES.get(t, t.replace("_", " ").title()) for t in types),
        "salary": j.get("salaryRangeText") or fact.get("salary") or "",
        "skills": [s.strip(" ,.") for s in (j.get("allSkills") or []) if s and s.strip(" ,.")],
        "posted_text": fact.get("postedDateLabel", "").replace("Posted ", ""),
        "posted_at": posted.isoformat(timespec="minutes") if posted else None,
        "posted_date": posted.date() if posted else None,
        "company_type": company.get("type") or "", "company_size": company.get("size") or "", "company_stage": company.get("stage") or "",
        "company_founded": company.get("founded"), "company_website": links.get("website") or "", "company_linkedin": links.get("linkedin") or "",
        "description": html_to_text(j.get("sanitizedComment") or ""),
        "source": "cutshort",
    }


def parse_page(page_html: str) -> tuple[list[dict], int | None]:
    """Jobs on one list page (newest first) and how many jobs the list holds in all."""
    data = _page_data(page_html)
    jobs = [job for j in data.get("jobs") or [] if (job := _job(j))]
    return jobs, data.get("liveJobCount")
