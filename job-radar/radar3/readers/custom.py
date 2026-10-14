"""Type C readers: big companies with their own career sites. Each reads the JSON that the career page itself loads (found once in development),
so no browser is needed at run time."""
import re
from datetime import datetime

from .common import make_job
from .keywords import ROLE_KEYWORDS

QUERIES = ROLE_KEYWORDS


def amazon(src: dict, http) -> list[dict]:
    """amazon.jobs/en/search.json, India only, 100 per page."""
    jobs, seen = [], set()
    for q in QUERIES:
        for page in range(5):
            _before = len(seen)
            data = http.get_json("https://www.amazon.jobs/en/search.json", params={"base_query": q, "loc_query": "India", "country": "IND", "result_limit": 100,
                                                                                  "offset": page * 100, "sort": "recent"})
            rows = data.get("jobs") or []
            for it in rows:
                jid = it.get("id_icims") or it.get("id")
                if jid in seen:
                    continue
                seen.add(jid)
                try:
                    posted = datetime.strptime(re.sub(r"\s+", " ", it.get("posted_date") or ""), "%B %d, %Y").date()
                except ValueError:
                    posted = None
                place = it.get("normalized_location") or ", ".join(x for x in (it.get("city"), it.get("state"), "India") if x)
                j = make_job(src, it.get("title"), "https://www.amazon.jobs" + (it.get("job_path") or f"/en/jobs/{jid}"), location=place.replace(", IND", ", India"),
                             posted=posted, job_id=jid, job_type=it.get("job_schedule_type") or "", skills=it.get("job_category") or "")
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < 100 or (page + 1) * 100 >= (data.get("hits") or 0):
                break
    return jobs


GOLDMAN_QUERY = ("query GetRoles($searchQueryInput: RoleSearchQueryInput!) { roleSearch(searchQueryInput: $searchQueryInput) { totalCount items "
                 "{ roleId jobTitle locations { city country state } externalSource { sourceId } division corporateTitle } } }")


def goldman(src: dict, http) -> list[dict]:
    """Goldman Sachs 'higher' GraphQL API, India filter, professional and early-career roles, several keywords."""
    jobs, seen = [], set()
    for q in ("data", "machine learning", "artificial intelligence", "analytics", "engineer"):          # Goldman gains nothing from the wider list (measured)
        for experience in ("PROFESSIONAL", "EARLY_CAREER"):
            for page in range(6):
                _before = len(seen)
                payload = {"operationName": "GetRoles", "query": GOLDMAN_QUERY, "variables": {"searchQueryInput": {
                    "page": {"pageSize": 20, "pageNumber": page}, "sort": {"sortStrategy": "POSTED_DATE", "sortOrder": "DESC"},
                    "filters": [{"filterCategoryType": "LOCATION", "filters": [{"filter": "India", "subFilters": []}]}], "experiences": [experience], "searchTerm": q}}}
                res = (http.post_json("https://api-higher.gs.com/gateway/api/v1/graphql", payload).get("data") or {}).get("roleSearch") or {}
                rows = res.get("items") or []
                for it in rows:
                    sid = (it.get("externalSource") or {}).get("sourceId") or it.get("roleId")
                    if sid in seen:
                        continue
                    seen.add(sid)
                    locs = [", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x) for loc in it.get("locations") or []]
                    j = make_job(src, it.get("jobTitle"), f"https://higher.gs.com/roles/{sid}", location=locs[0] if locs else "India", more="; ".join(locs[1:]), job_id=sid,
                                 job_type=it.get("corporateTitle") or "")
                    if j:
                        jobs.append(j)
                if len(seen) == _before:
                    break
                if len(rows) < 20 or (page + 1) * 20 >= (res.get("totalCount") or 0):
                    break
    return jobs


def deutsche(src: dict, http) -> list[dict]:
    """Deutsche Bank careers search API, India (country code 81), all roles in pages of 100."""
    jobs, first = [], 1
    for _ in range(10):
        body = {"SearchParameters": {"FirstItem": first, "CountItem": 100, "Sort": [{"Criterion": "PublicationStartDate", "Direction": "DESC"}],
                                     "MatchedObjectDescriptor": ["ID", "PositionTitle", "PositionURI", "PositionLocation.CountryName", "PositionLocation.CityName",
                                                                 "PositionLocation.CountryCode", "PublicationStartDate"]},
                "SearchCriteria": [{"CriterionName": "PositionLocation.Country", "CriterionValue": ["81"]}]}
        res = http.post_json("https://api-deutschebank.beesite.de/search/", body).get("SearchResult") or {}
        rows = res.get("SearchResultItems") or []
        for it in rows:
            d = it.get("MatchedObjectDescriptor") or {}
            jid = it.get("MatchedObjectId") or re.sub(r"\D", "", d.get("PositionURI", ""))
            locs = [", ".join(x for x in (loc.get("CityName"), "India" if loc.get("CountryCode") == "IN" else loc.get("CountryName")) if x) for loc in d.get("PositionLocation") or []]
            j = make_job(src, d.get("PositionTitle"), f"https://careers.db.com/professionals/search-roles/#/professional/job/{jid}", location=locs[0] if locs else "India",
                         more="; ".join(locs[1:]), posted=d.get("PublicationStartDate"), job_id=jid)
            if j:
                jobs.append(j)
        first += len(rows)
        if len(rows) < 100 or first > (res.get("SearchResultCountAll") or 0):
            break
    return jobs


def parse_apple(html: str) -> tuple[list[dict], int]:
    """(search results, total) from the JSON that jobs.apple.com puts in its search page (window.__staticRouterHydrationData)."""
    import json
    m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);', html, re.S)
    if not m:
        return [], 0
    data = json.loads(m.group(1).encode().decode("unicode_escape"))
    search = (data.get("loaderData") or {}).get("search") or {}
    return search.get("searchResults") or [], int(search.get("totalRecords") or 0)


def apple(src: dict, http) -> list[dict]:
    """jobs.apple.com India search, 20 per page, several keywords."""
    from urllib.parse import quote
    jobs, seen = [], set()
    for q in ROLE_KEYWORDS:
        for page in range(1, 7):
            _before = len(seen)
            rows, total = parse_apple(http.get_text(f"https://jobs.apple.com/en-in/search?search={quote(q)}&location=india-INDC&page={page}"))
            for it in rows:
                pid = it.get("positionId")
                if pid in seen:
                    continue
                seen.add(pid)
                spots = [", ".join(x for x in (loc.get("name"), loc.get("countryName")) if x) for loc in it.get("locations") or []]
                j = make_job(src, it.get("postingTitle"), f"https://jobs.apple.com/en-in/details/{pid}/{it.get('transformedPostingTitle', '')}", location=spots[0] if spots else "India",
                             more="; ".join(spots[1:]), posted=it.get("postDateInGMT"), job_id=pid)
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < 20 or page * 20 >= total:
                break
    return jobs


def parse_google(html: str) -> tuple[list[list], int]:
    """(job rows, total) from the AF_initDataCallback 'ds:1' block that google.com/about/careers puts in its results page.
    Row fields used: 0 id, 1 title, 7 team, 9 locations [[full name, [address], city, zip, state, country]], 12 [created epoch seconds, ...]."""
    import json
    m = re.search(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*?), sideChannel: \{\}\}\);</script>", html, re.S)
    if not m:
        return [], 0
    data = json.loads(m.group(1))
    rows = data[0] if data and isinstance(data[0], list) else []
    total = data[2] if len(data) > 2 and isinstance(data[2], int) else 0
    return rows, total


def google(src: dict, http) -> list[dict]:
    """Google Careers India search: the jobs are inside the results page's own data block (no browser, no hidden request). 20 per page."""
    from urllib.parse import quote
    jobs, seen = [], set()
    for q in ROLE_KEYWORDS:
        for page in range(1, 8):
            _before = len(seen)
            rows, total = parse_google(http.get_text(f"https://www.google.com/about/careers/applications/jobs/results/?location=India&q={quote(q)}&page={page}"))
            for r in rows:
                jid = r[0]
                if jid in seen:
                    continue
                seen.add(jid)
                spots = [str(loc[0]) for loc in (r[9] if len(r) > 9 and isinstance(r[9], list) else []) if loc]
                created = r[12][0] if len(r) > 12 and isinstance(r[12], list) and r[12] else None
                j = make_job(src, r[1], f"https://www.google.com/about/careers/applications/jobs/results/{jid}", location=spots[0] if spots else "India",
                             more="; ".join(spots[1:]), posted=created, job_id=jid, job_type=str(r[7]) if len(r) > 7 and r[7] else "")
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < 20 or page * 20 >= total:
                break
    return jobs


META_INDIA_OFFICES = ("Bangalore, India", "Mumbai, India", "Gurugram, India", "Hyderabad, India", "New Delhi, India")


def meta(src: dict, http) -> list[dict]:
    """Meta Careers: the page's own GraphQL call, replayed with plain requests. slug = the query's doc_id (found with the Playwright CLI:
    request-body of CareersJobSearchResultsV2DataQuery). The page gives a session token (LSD); one call per India office lists all its jobs."""
    import json
    html = http.get_text("https://www.metacareers.com/jobsearch/")
    m = re.search(r'"LSD",\[\],\{"token":"([^"]+)"', html)
    if not m:
        return []
    lsd, jobs, seen = m.group(1), [], set()
    for office in META_INDIA_OFFICES:
        variables = {"search_input": {"q": "", "divisions": [], "offices": [office], "roles": [], "leadership_levels": [], "saved_jobs": [], "saved_searches": [],
                                      "sub_teams": [], "teams": [], "is_leadership": False, "is_remote_only": False, "sort_by_new": False, "results_per_page": None},
                     "viewasUserID": None, "isLoggedIn": False}
        data = http.post_form("https://www.metacareers.com/graphql", {"fb_api_caller_class": "RelayModern", "fb_api_req_friendly_name": "CareersJobSearchResultsV2DataQuery",
                                                                     "variables": json.dumps(variables), "server_timestamps": "true", "doc_id": src["slug"], "lsd": lsd},
                              headers={"X-FB-LSD": lsd})
        for it in ((data.get("data") or {}).get("job_search_with_featured_jobs_v2") or {}).get("all_jobs") or []:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            spots = it.get("locations") or [office]
            j = make_job(src, it.get("title"), f"https://www.metacareers.com/jobs/{it['id']}", location=spots[0], more="; ".join(spots[1:]), job_id=it["id"],
                         skills=", ".join((it.get("teams") or []) + (it.get("sub_teams") or [])))
            if j:
                jobs.append(j)
    return jobs


def ibm(src: dict, http) -> list[dict]:
    """IBM Careers search API (www-api.ibm.com/search/api/v2), India filter. The request body was copied from the page's own call with the Playwright CLI."""
    jobs, seen = [], set()
    fields = ["keywords^1", "body^1", "url^2", "description^2", "h1s_content^2", "title^3", "field_text_01"]
    for q in ROLE_KEYWORDS:
        for page in range(5):
            _before = len(seen)
            body = {"appId": "careers", "scopes": ["careers2"], "query": {"bool": {"must": [{"simple_query_string": {"query": q, "fields": fields}}]}},
                    "post_filter": {"term": {"field_keyword_05": "India"}}, "size": 30, "from": page * 30, "sort": [{"_score": "desc"}, {"pageviews": "desc"}],
                    "lang": "zz", "localeSelector": {}, "sm": {"query": q, "lang": "zz"},
                    "_source": ["_id", "title", "url", "description", "language", "entitled", "field_keyword_17", "field_keyword_08", "field_keyword_18", "field_keyword_19"]}
            hits = (http.post_json("https://www-api.ibm.com/search/api/v2", body).get("hits") or {})
            rows = hits.get("hits") or []
            for h in rows:
                it = h.get("_source") or {}
                jid = h.get("_id") or it.get("url")
                if jid in seen:
                    continue
                seen.add(jid)
                place = re.sub(r",\s*IN$", ", India", it.get("field_keyword_19") or "")
                mode = it.get("field_keyword_17") or ""
                j = make_job(src, it.get("title"), it.get("url"), location=place or "India", remote=mode.lower() == "remote", job_id=jid,
                             work_mode=mode if mode.lower() in ("remote", "hybrid", "onsite") else "", skills=it.get("field_keyword_08") or "", experience=it.get("field_keyword_18") or "")
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < 30 or (page + 1) * 30 >= ((hits.get("total") or {}).get("value") or 0):
                break
    return jobs


def capgemini(src: dict, http) -> list[dict]:
    """Capgemini India job search API (cg-jobstream-api.azurewebsites.net), 100 per page."""
    jobs, seen = [], set()
    for q in ROLE_KEYWORDS:
        for page in range(1, 6):
            _before = len(seen)
            data = http.get_json("https://cg-jobstream-api.azurewebsites.net/api/job-search", params={"page": page, "size": 100, "country_code": "in-en", "search": q})
            rows = data.get("data") or []
            for it in rows:
                jid = it.get("ref") or it.get("id")
                if jid in seen:
                    continue
                seen.add(jid)
                place = it.get("location") or ""
                j = make_job(src, it.get("title"), it.get("apply_job_url") or f"https://careers.capgemini.com/job/{jid}", location=f"{place}, India" if place else "India",
                             posted=it.get("updated_at"), job_id=jid, job_type=it.get("contract_type") or "", skills=it.get("professional_communities") or "",
                             experience=it.get("experience_level") or "")
                if j:
                    jobs.append(j)
            if len(seen) == _before:
                break
            if len(rows) < 100 or page * 100 >= (data.get("total") or 0):
                break
    return jobs


def infosys(src: dict, http) -> list[dict]:
    """Infosys careers: the page's own unauthenticated search call returns every open job in one JSON list (about 5 MB). India roles only."""
    jobs = []
    for it in http.get_json("https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs", params={"sourceId": "1,21", "searchText": "ALL"}):
        ref = it.get("referenceCode") or it.get("requisitionId")
        lo, hi = it.get("minExperienceLevel"), it.get("maxExperienceLevel")
        place = (it.get("location") or "").strip().title()
        j = make_job(src, it.get("postingTitle"), f"https://career.infosys.com/jobdesc?jobReferenceCode={ref}", location=f"{place}, {it.get('country') or 'India'}" if place else "India",
                     posted=it.get("createdOn"), job_id=ref, skills=it.get("functionalArea") or "", experience=f"{lo}-{hi} yrs" if lo is not None and hi is not None else "",
                     job_type=it.get("roleDesignation") or "")
        if j:
            jobs.append(j)
    return jobs


def consider(src: dict, http) -> list[dict]:
    """Venture-capital portfolio boards on the Consider platform (Sequoia, Bessemer, First Round, Kleiner Perkins...): POST /api-boards/search-jobs, filtered to
    India, 100 per page. slug = 'host|board id'. The page gives a CSRF token and a session cookie, so the page and the search use the same session."""
    host, board = src["slug"].split("|")
    html = http.get_text(f"https://{host}/jobs")
    m = re.search(r"csrf[-_]?token[\"']?\s*[:=]\s*[\"']([^\"']+)", html, re.I)
    if not m:
        return []
    headers = {"X-CSRF-Token": m.group(1), "Origin": f"https://{host}", "Referer": f"https://{host}/jobs", "Accept": "application/json"}
    jobs, seen, sequence = [], set(), None
    for page in range(12):
        meta = {"size": 100}
        if sequence:
            meta["sequence"] = sequence                      # the page token from the previous answer ('from' returns the same jobs again)
        body = {"meta": meta, "board": {"id": board, "isParent": True}, "query": {"locations": ["India"]}, "grouped": False}
        data = http.post_json(f"https://{host}/api-boards/search-jobs", body, headers=headers)
        sequence = (data.get("meta") or {}).get("sequence")
        rows = data.get("jobs") or []
        for it in rows:
            jid = it.get("jobId") or it.get("applyUrl")
            if jid in seen:
                continue
            seen.add(jid)
            spots = it.get("locations") or []
            yrs = it.get("minYearsExp")
            j = make_job(src, it.get("title"), it.get("applyUrl") or it.get("url"), location=spots[0] if spots else "India", more="; ".join(spots[1:]), remote=bool(it.get("remote")),
                         company=it.get("companyName"), posted=it.get("timeStamp"), job_id=jid, experience=f"{yrs}+ yrs" if yrs else "")
            if j:
                jobs.append(j)
        if len(rows) < 100 or not sequence or (page + 1) * 100 >= (data.get("total") or 0):
            break
    return jobs


def affine(src: dict, http) -> list[dict]:
    """Affine's careers page reads a small jobs.json."""
    jobs = []
    for it in (http.get_json("https://affine.ai/data/jobs.json").get("jobs") or []):
        j = make_job(src, it.get("title"), it.get("applyUrl") or "https://affine.ai/careers/", location=f"{it.get('location')}, India" if it.get("location") else "India",
                     job_id=it.get("code"), experience=it.get("experience") or "", job_type=it.get("type") or "", work_mode=it.get("workplace") or "",
                     skills=it.get("department") or "")
        if j:
            jobs.append(j)
    return jobs


GETRO_QUERIES = ("data scientist", "machine learning", "data engineer", "ai engineer", "analyst")


def getro(src: dict, http) -> list[dict]:
    """Venture-capital portfolio boards on the Getro platform (General Catalyst, Accel, NFX...): the public search API of the board's collection, India only.
    The API serves 20 jobs per page whatever the size asked, and these boards hold thousands of jobs, so three role keywords are searched (most relevant first,
    up to 20 pages each). slug = the collection id (found in the board page)."""
    jobs, seen = [], set()
    for q in GETRO_QUERIES:
        for page in range(20):
            _before = len(seen)
            res = (http.post_json(f"https://api.getro.com/api/v2/collections/{src['slug']}/search/jobs",
                                  {"hitsPerPage": 20, "page": page, "query": q, "filters": {"searchable_locations": ["India"]}},
                                  headers={"Accept": "application/json"}).get("results") or {})
            rows, fresh = res.get("jobs") or [], 0
            for it in rows:
                jid = it.get("id") or it.get("url")
                if jid in seen:
                    continue
                seen.add(jid)
                fresh += 1
                spots = it.get("locations") or []
                mode = it.get("work_mode") or ""
                j = make_job(src, it.get("title"), it.get("url"), location=spots[0] if spots else "India", more="; ".join(spots[1:]), remote=mode == "remote",
                             company=(it.get("organization") or {}).get("name"), posted=it.get("created_at"), job_id=jid,
                             work_mode={"remote": "Remote", "hybrid": "Hybrid", "on_site": "Onsite"}.get(mode, ""), skills=it.get("skills") or [], experience=it.get("seniority") or "")
                if j:
                    jobs.append(j)
            if not rows or not fresh or (page + 1) * 20 >= (res.get("count") or 0):
                break
    return jobs


YC_PAGES = ("india", "bengaluru", "mumbai", "new-delhi", "hyderabad", "pune", "gurugram", "noida")


def parse_yc(html_text: str) -> list[dict]:
    """The jobs inside a ycombinator.com/jobs page: the page's own data-page attribute (Inertia) holds props.jobPostings."""
    import html as htmllib
    import json
    m = re.search(r'data-page="([^"]+)"', html_text)
    if not m:
        return []
    try:
        return (json.loads(htmllib.unescape(m.group(1))).get("props") or {}).get("jobPostings") or []
    except ValueError:
        return []


def yc_jobs(src: dict, http) -> list[dict]:
    """Y Combinator startup jobs in India. The site shows up to about 50 jobs per page and loads no more when scrolled, so the Indian city pages are read one by one
    (Bengaluru, Mumbai, New Delhi, Hyderabad, Pune, Gurugram, Noida and the India page) and merged. No browser needed."""
    jobs, seen = [], set()
    for slug in (src.get("slug") or ",".join(YC_PAGES)).split(","):
        for it in parse_yc(http.get_text(f"https://www.ycombinator.com/jobs/location/{slug.strip()}")):
            jid = it.get("id")
            if jid in seen:
                continue
            seen.add(jid)
            spots = [x.strip() for x in (it.get("location") or "").split(" / ") if x.strip()]
            spots = [re.sub(r",\s*IN\b", ", India", s) if s != "IN" else "India" for s in spots]
            j = make_job(src, it.get("title"), "https://www.ycombinator.com" + (it.get("url") or ""), location=spots[0] if spots else "", more="; ".join(spots[1:]),
                         remote="remote" in (it.get("location") or "").lower(), company=it.get("companyName"), job_id=jid, salary=it.get("salaryRange") or "",
                         experience=it.get("minExperience") or "", job_type=it.get("type") or "", skills=it.get("prettyRole") or "")
            if j:
                jobs.append(j)
    return jobs
