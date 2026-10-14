"""Type B readers for the big-company career platforms: Phenom, Eightfold, Oracle HCM. A company is one line in sources.csv (the slug).
Each reader asks the platform's own public search API (the one the career page itself calls), for a few AI/ML/Data keywords."""
from urllib.parse import quote

from .common import make_job, parse_date
from .keywords import ROLE_KEYWORDS

QUERIES = ROLE_KEYWORDS
MAX_PAGES = 4


def phenom_widget(src: dict, http) -> list[dict]:
    """Phenom People sites. slug = 'host|refNum|lang|path', e.g. careers.wbd.com|WAMEGLOBAL|en_global|global/en. Filtered to India server-side."""
    host, ref, lang, path = src["slug"].split("|")
    size, jobs, seen = 50, [], set()
    for q in QUERIES:
        for page in range(MAX_PAGES):
            _before = len(seen)
            body = {"lang": lang, "deviceType": "desktop", "country": path.split("/")[0], "pageName": "search-results", "ddoKey": "refineSearch", "sortBy": "",
                    "subsearch": "", "from": page * size, "jobs": True, "counts": True, "all_fields": ["category", "country", "state", "city", "type"],
                    "size": size, "clearAll": False, "jdsource": "facets", "isSliderEnable": False, "pageId": "page1", "siteType": "external",
                    "keywords": q, "global": True, "selected_fields": {"country": ["India"]}, "sort": {"order": "desc", "field": "postedDate"},
                    "locationData": {}, "refNum": ref}
            rs = http.post_json(f"https://{host}/widgets", body).get("refineSearch", {})
            rows = (rs.get("data") or {}).get("jobs") or []
            for it in rows:
                jid = it.get("jobSeqNo") or it.get("jobId") or it.get("reqId")
                if jid in seen:
                    continue
                seen.add(jid)
                place = it.get("cityStateCountry") or it.get("location") or ""
                more = "; ".join(x for x in (it.get("multi_location") or []) if x != place)
                j = make_job(src, it.get("title"), it.get("applyUrl") or f"https://{host}/{path}/job/{jid}", location=place, more=more,
                             posted=it.get("postedDate") or it.get("dateCreated"), job_id=jid, job_type=it.get("type") or "")
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < size or (page + 1) * size >= (rs.get("totalHits") or 0):
                break
    return jobs


def eightfold(src: dict, http) -> list[dict]:
    """Eightfold career sites. slug = 'host|domain|style' with style 'pcsx' (/api/pcsx/search) or 'apply' (/api/apply/v2/jobs)."""
    host, domain, style = src["slug"].split("|")
    jobs, seen = [], set()
    for q in QUERIES:
        for page in range(MAX_PAGES):
            _before = len(seen)
            if style == "pcsx":
                data = http.get_json(f"https://{host}/api/pcsx/search", params={"domain": domain, "query": q, "location": "India", "start": page * 10})
                rows, total = (data.get("data") or {}).get("positions") or [], (data.get("data") or {}).get("count") or 0
            else:
                data = http.get_json(f"https://{host}/api/apply/v2/jobs", params={"domain": domain, "query": q, "start": page * 10, "num": 10})
                rows, total = data.get("positions") or [], data.get("count") or 0
            for it in rows:
                jid = it.get("id")
                if jid in seen:
                    continue
                seen.add(jid)
                locs = it.get("locations") or ([it["location"]] if it.get("location") else [])
                mode = (it.get("workLocationOption") or it.get("work_location_option") or "").lower()
                url = f"https://{host}{it['positionUrl']}" if it.get("positionUrl") else f"https://{host}/careers/job/{jid}"
                j = make_job(src, it.get("name") or it.get("posting_name"), url, location=locs[0] if locs else "", more="; ".join(locs[1:]),
                             remote=mode == "remote", posted=it.get("postedTs") or it.get("t_create"), job_id=jid,
                             work_mode=mode.capitalize() if mode in ("remote", "hybrid", "onsite") else "")
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < 10 or (page + 1) * 10 >= total:
                break
    return jobs


def oracle_hcm(src: dict, http) -> list[dict]:
    """Oracle HCM candidate experience (recruitingCEJobRequisitions). slug = 'host|siteNumber', e.g. jpmc.fa.oraclecloud.com|CX_1001.
    The id of the 'India' location is read once from the locations facet and then used as a filter."""
    host, site = src["slug"].split("|")
    base = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations,locationsFacet&finder="

    def search(q: str, limit: int, offset: int, extra: str = "") -> dict:
        data = http.get_json(f"{base}findReqs;siteNumber={site},limit={limit},offset={offset},keyword={quote(q)},sortBy=POSTING_DATES_DESC{extra}")
        return (data.get("items") or [{}])[0]

    facets = search(QUERIES[0], 1, 0).get("locationsFacet") or []
    india = next((f["Id"] for f in facets if str(f.get("Name", "")).strip().lower() == "india"), None)
    extra = f",selectedLocationsFacet={india}" if india else ""
    jobs, seen, limit = [], set(), 25
    for q in QUERIES:
        for page in range(MAX_PAGES):
            _before = len(seen)
            item = search(q, limit, page * limit, extra)
            rows = item.get("requisitionList") or []
            for it in rows:
                jid = it.get("Id")
                if jid in seen:
                    continue
                seen.add(jid)
                spots = [it.get("PrimaryLocation", "")] + [s.get("Name", "") for s in it.get("secondaryLocations") or [] if isinstance(s, dict)]
                j = make_job(src, it.get("Title"), f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{jid}", location=spots[0],
                             more="; ".join(x for x in spots[1:] if x), remote=(it.get("WorkplaceTypeCode") or "").upper() == "ORA_REMOTE",
                             posted=it.get("PostedDate"), job_id=jid)
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < limit or (page + 1) * limit >= (item.get("TotalJobsCount") or 0):
                break
    return jobs
