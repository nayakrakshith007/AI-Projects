"""Type A readers: public job feeds and APIs. No browser, one or a few requests each."""
import html
import re
import xml.etree.ElementTree as ET

from .common import make_job, strip_html


def _salary(lo, hi, cur="$") -> str:
    lo, hi = int(lo or 0), int(hi or 0)
    return f"{cur}{lo:,}-{cur}{hi:,}" if lo and hi else f"{cur}{lo or hi:,}" if lo or hi else ""


def remoteok(src: dict, http) -> list[dict]:
    """remoteok.com/api. The first element is a legal notice. RemoteOK asks for a link back, so the job link is kept as is."""
    data = http.get_json("https://remoteok.com/api")
    jobs = []
    for it in data:
        if not isinstance(it, dict) or not it.get("position"):
            continue
        j = make_job(src, it["position"], it.get("url") or it.get("apply_url"), location=it.get("location") or "", remote=True, company=it.get("company"),
                     posted=it.get("date") or it.get("epoch"), job_id=it.get("id"), skills=it.get("tags") or [],
                     salary=_salary(it.get("salary_min"), it.get("salary_max")))
        if j:
            jobs.append(j)
    return jobs


def remotive(src: dict, http) -> list[dict]:
    """remotive.com/api/remote-jobs, one call per category in the source's slug (comma separated). Remotive asks for few calls a day."""
    jobs, seen = [], set()
    for cat in (src.get("slug") or "software-dev,data").split(","):
        data = http.get_json("https://remotive.com/api/remote-jobs", params={"category": cat.strip(), "limit": 100})
        for it in data.get("jobs", []):
            if it.get("id") in seen:
                continue
            seen.add(it.get("id"))
            j = make_job(src, it.get("title"), it.get("url"), location=it.get("candidate_required_location") or "", remote=True,
                         company=it.get("company_name"), posted=it.get("publication_date"), job_id=it.get("id"), skills=it.get("tags") or [],
                         salary=it.get("salary") or "", job_type=(it.get("job_type") or "").replace("_", " "))
            if j:
                jobs.append(j)
    return jobs


def workingnomads(src: dict, http) -> list[dict]:
    jobs = []
    for it in http.get_json("https://www.workingnomads.com/api/exposed_jobs/"):
        tags = it.get("tags") or ""
        j = make_job(src, it.get("title"), it.get("url"), location=it.get("location") or "", remote=True, company=it.get("company_name"),
                     posted=it.get("pub_date"), skills=[t.strip() for t in tags.split(",")] if isinstance(tags, str) else tags)
        if j:
            jobs.append(j)
    return jobs


def rss_items(xml_text: str) -> list[dict]:
    """RSS items as {local tag name: text}."""
    root = ET.fromstring(xml_text.lstrip())
    return [{re.sub(r"^\{.*\}", "", c.tag): (c.text or "").strip() for c in it} for it in root.iter("item")]


def weworkremotely(src: dict, http) -> list[dict]:
    """We Work Remotely RSS. The slug lists feed paths (comma separated); titles look like 'Company: Title'."""
    jobs, seen = [], set()
    for path in (src.get("slug") or "remote-jobs.rss").split(","):
        for it in rss_items(http.get_text("https://weworkremotely.com/" + path.strip().lstrip("/"))):
            link = it.get("link") or it.get("guid")
            if link in seen:
                continue
            seen.add(link)
            company, _, title = it.get("title", "").partition(": ")
            if not title:
                company, title = "", company
            where = ", ".join(x for x in (it.get("region"), it.get("country"), it.get("state")) if x)
            j = make_job(src, title, link, location=where, remote=True, company=company or None, posted=it.get("pubDate"), job_type=it.get("type", ""),
                         skills=[s.strip() for s in it.get("skills", "").split(",") if s.strip()])
            if j:
                jobs.append(j)
    return jobs


def jobspresso(src: dict, http) -> list[dict]:
    """Jobspresso RSS. The creator field holds 'Company<br>(pin) Location'."""
    jobs = []
    for it in rss_items(http.get_text("https://jobspresso.co/feed/?post_type=job_listing")):
        company, _, place = re.sub(r"<br\s*/?>", "\n", it.get("creator", "")).partition("\n")
        place = re.sub(r"^[^\w]+", "", html.unescape(strip_html(place)).replace("\xa0", " ")).strip()
        j = make_job(src, strip_html(it.get("title", "")), it.get("link"), location=place, remote=True, company=strip_html(company) or None,
                     posted=it.get("pubDate"))
        if j:
            jobs.append(j)
    return jobs
