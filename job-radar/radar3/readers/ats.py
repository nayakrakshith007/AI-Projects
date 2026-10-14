"""Type B readers: the public APIs of job platforms. A company is one line in sources.csv (the slug)."""
import re
from datetime import date

from .common import days_ago, make_job
from .keywords import ROLE_KEYWORDS

WORKDAY_QUERIES = ROLE_KEYWORDS
WORKDAY_PAGE = 20
WORKDAY_MAX_PAGES = 5


def greenhouse(src: dict, http) -> list[dict]:
    data = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{src['slug']}/jobs")
    jobs = []
    for it in data.get("jobs", []):
        place = (it.get("location") or {}).get("name", "")
        j = make_job(src, it.get("title"), it.get("absolute_url"), location=place, remote=bool(re.search(r"remote", place, re.I)),
                     company=it.get("company_name"), posted=it.get("first_published") or it.get("updated_at"), job_id=it.get("id"))
        if j:
            jobs.append(j)
    return jobs


def ashby(src: dict, http) -> list[dict]:
    data = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{src['slug']}")
    jobs = []
    for it in data.get("jobs", []):
        if it.get("isListed") is False:
            continue
        more = "; ".join(s.get("location", "") for s in it.get("secondaryLocations") or [] if isinstance(s, dict))
        mode = (it.get("workplaceType") or "").strip()
        j = make_job(src, it.get("title"), it.get("jobUrl") or it.get("applyUrl"), location=it.get("location") or "", more=more,
                     remote=bool(it.get("isRemote")) or mode.lower() == "remote", posted=it.get("publishedAt"), job_id=it.get("id"),
                     work_mode=mode, job_type=it.get("employmentType") or "")
        if j:
            jobs.append(j)
    return jobs


def lever(src: dict, http) -> list[dict]:
    data = http.get_json(f"https://api.lever.co/v0/postings/{src['slug']}", params={"mode": "json"})
    jobs = []
    for it in data:
        cat = it.get("categories") or {}
        spots = cat.get("allLocations") or [cat.get("location", "")]
        mode = (it.get("workplaceType") or "").strip()
        j = make_job(src, it.get("text"), it.get("hostedUrl"), location=spots[0] if spots else "", more="; ".join(spots[1:]),
                     remote=mode.lower() == "remote", posted=it.get("createdAt"), job_id=it.get("id"), work_mode=mode.capitalize(),
                     job_type=cat.get("commitment", ""))
        if j:
            jobs.append(j)
    return jobs


def workable(src: dict, http) -> list[dict]:
    data = http.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{src['slug']}")
    jobs = []
    for it in data.get("jobs", []):
        place = ", ".join(x for x in (it.get("city"), it.get("state"), it.get("country")) if x)
        j = make_job(src, it.get("title"), it.get("url") or it.get("shortlink"), location=place, remote=bool(it.get("telecommuting")),
                     posted=it.get("published_on") or it.get("created_at"), job_id=it.get("shortcode"), job_type=it.get("employment_type") or "")
        if j:
            jobs.append(j)
    return jobs


def _workday_india_filter(facets: list) -> dict:
    """{'<facetParameter>': ['<India id>', ...]} from a Workday response's facets: the 'India' value of a country facet, or else every location
    whose name mentions India ('India - Chennai'). {} when the site offers neither."""
    country, spots = {}, []
    stack = list(facets or [])
    while stack:
        f = stack.pop()
        if not isinstance(f, dict):
            continue
        param = str(f.get("facetParameter", ""))
        for v in f.get("values") or []:
            name = str(v.get("descriptor", "")).strip().lower()
            if not v.get("id"):
                continue
            if "ountry" in param and name == "india":
                country = {param: [v["id"]]}
            elif param == "locations" and re.search(r"\bindia\b", name):
                spots.append((param, v["id"]))
        stack.extend(f.get("values") or [])
    if country:
        return country
    return {"locations": [i for _, i in spots]} if spots else {}


def workday(src: dict, http, today: date | None = None) -> list[dict]:
    """Workday 'cxs' search. slug = 'host|tenant|site', e.g. cat.wd5.myworkdayjobs.com|cat|CaterpillarCareers. Several keyword searches are merged.
    When the site has a country facet the searches are limited to India."""
    host, tenant, site = src["slug"].split("|")
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    first = http.post_json(api, {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": WORKDAY_QUERIES[0]})
    applied = _workday_india_filter(first.get("facets"))
    jobs, seen = [], set()
    for q in WORKDAY_QUERIES:
        for page in range(WORKDAY_MAX_PAGES):
            _before = len(seen)
            data = http.post_json(api, {"appliedFacets": applied, "limit": WORKDAY_PAGE, "offset": page * WORKDAY_PAGE, "searchText": q})
            posts = data.get("jobPostings") or []
            for it in posts:
                path = it.get("externalPath", "")
                if path in seen:
                    continue
                seen.add(path)
                where = it.get("locationsText", "")
                if not where and path.startswith("/job/"):                 # some tenants (Accenture) give only the city, inside the link
                    where = path.split("/")[2].replace("-", " ") + (", India" if applied else "")
                j = make_job(src, it.get("title"), f"https://{host}/en-US/{site}{path}", location=where, remote=bool(re.search(r"remote", where, re.I)),
                             posted=days_ago(it.get("postedOn", ""), today), job_id=(it.get("bulletFields") or [path])[0])
                if j:
                    if re.match(r"\d+ locations?", where, re.I):          # the real places are on the job page: keep, flagged
                        j.update(tier=4, eligibility="unclear")
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(posts) < WORKDAY_PAGE or (page + 1) * WORKDAY_PAGE >= (data.get("total") or 0):
                break
    return jobs


def smartrecruiters(src: dict, http) -> list[dict]:
    """SmartRecruiters public postings API, filtered to India. slug = the company identifier (e.g. Swiggy)."""
    jobs, limit = [], 100
    for page in range(10):
        data = http.get_json(f"https://api.smartrecruiters.com/v1/companies/{src['slug']}/postings", params={"limit": limit, "offset": page * limit, "country": "in"})
        rows = data.get("content") or []
        for it in rows:
            loc = it.get("location") or {}
            place = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("region"), "India" if (loc.get("country") or "").lower() == "in" else (loc.get("country") or "").upper()) if x)
            j = make_job(src, it.get("name"), f"https://jobs.smartrecruiters.com/{(it.get('company') or {}).get('identifier') or src['slug']}/{it.get('id')}",
                         location=place, remote=bool(loc.get("remote")), posted=it.get("releasedDate"), job_id=it.get("id"),
                         job_type=(it.get("typeOfEmployment") or {}).get("label", ""))
            if j:
                jobs.append(j)
        if len(rows) < limit or (page + 1) * limit >= (data.get("totalFound") or 0):
            break
    return jobs
