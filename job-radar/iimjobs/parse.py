"""Turn the JSON an IIMJobs list page loads for itself into plain job dicts. Pure functions.

Both the tag pages (/k/<tag>-jobs) and the search pages (/search/<keyword>-jobs) load the same job format from gladiator.iimjobs.com.
The recruiter side of the data (who posted a job) is not read or kept."""
import math
import re
from datetime import datetime, timedelta, timezone

from common.geo import is_bengaluru

from . import config

IST = timezone(timedelta(hours=5, minutes=30))


def split_title(raw: str, company: str = "") -> tuple[str, str]:
    """IIMJobs titles read 'Company - Role - Detail', or just 'Role - Detail' for confidential employers.
    Returns (company, role title); the company the employer registered wins when the title has no matching prefix."""
    raw = (raw or "").strip()
    head, sep, rest = raw.partition(" - ")
    if sep and (not company or company.lower().startswith(head.lower()) or head.lower() in company.lower()):
        return (company or head).strip(), rest.strip()
    return company.strip(), raw


def job_url(title: str, job_id) -> str:
    """The address IIMJobs itself uses: /j/<title words>-<id> ('&' becomes 'and')."""
    words = re.sub(r"[^a-z0-9]+", "-", (title or "").lower().replace("&", " and ")).strip("-")
    return f"{config.BASE}/j/{words}-{job_id}" if words else f"{config.BASE}/j/{job_id}"


def _exp(lo, hi) -> tuple[int | None, int | None, str]:
    """Experience numbers and text. 0-0 or missing means nothing was stated."""
    lo = None if lo in (None, "") else int(lo)
    hi = None if hi in (None, "") else int(hi)
    if not lo and not hi:
        return None, None, ""
    hi = hi if hi and hi >= (lo or 0) else lo
    return lo, hi, f"{lo or 0}-{hi} years" if hi != lo else f"{lo}+ years"


def total_pages(data: dict) -> int | None:
    """Pages the list has, from the number of jobs and the page size. IIMJobs' own totalPages field is wrong when the date filter
    is on (it said 1 for 89 jobs, and 0 for 12), so it is only used when the job count is missing."""
    total, size = data.get("totalJobs"), data.get("limit") or config.PAGE_SIZE
    if total:
        return math.ceil(total / size)
    return data.get("totalPages") or None


def parse_json(data: dict) -> list[dict]:
    """Jobs from one page of the list JSON: exact posting time, numeric experience, every location."""
    jobs = []
    for j in data.get("data") or []:
        if not j.get("id") or not j.get("title"):
            continue
        company_data = j.get("companyData") or {}
        company, title = split_title(j["title"], company_data.get("companyName", ""))
        lo, hi, shown = _exp(j.get("min"), j.get("max"))
        locations = [x["name"] for x in (j.get("locations") or j.get("location") or []) if x.get("name")]
        created = j.get("createdTimeMs")
        posted_at = datetime.fromtimestamp(created / 1000, IST) if created else None
        salary = f"{j['minSal']}-{j['maxSal']} LPA" if not j.get("hideSal") and (j.get("minSal") or j.get("maxSal")) else ""
        jobs.append({
            "id": str(j["id"]), "url": job_url(j["title"], j["id"]), "title": title, "company": company,
            "designation": j.get("jobdesignation") or "",
            "experience": shown, "experience_min": lo, "experience_max": hi,
            "locations": locations, "location": ", ".join(locations), "bengaluru": "Yes" if any(is_bengaluru(x) for x in locations) else "",
            "work_mode": "Work from home" if j.get("workFromHome") else "", "salary": salary,
            "skills": [t["name"] for t in j.get("tags") or [] if t.get("name")],
            "posted_date": posted_at.date() if posted_at else None, "posted_at": posted_at.isoformat(timespec="minutes") if posted_at else None,
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
