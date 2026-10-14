"""Remove duplicates across sites: the same opening posted on Naukri, LinkedIn and Hirist becomes one row that lists every site.

Two jobs are the same when they have the same link, or the same title (after normalising) at the same company at an overlapping
place. Company names are compared without legal suffixes and a name that is a whole-word prefix of another counts as the same
('Tredence' = 'Tredence Analytics Solutions Private Limited'). Jobs with no company are never merged by title. Places overlap when
they share a city; an unknown or generic place ('India', 'Remote') overlaps with anything."""
import re
from datetime import date

from . import config

LEGAL = {"pvt", "private", "ltd", "limited", "llp", "inc", "incorporated", "corp", "corporation", "llc", "plc", "opc", "co", "the"}
GENERIC_PLACE = {"india", "remote", "anywhere", "pan", "hybrid", "work", "from", "home", "wfh", "onsite", "wfo", "or", "and", "only", "in",
                 "greater", "area", "urban", "rural", "region", "metropolitan", "district", "state",
                 "karnataka", "telangana", "maharashtra", "tamil", "nadu", "haryana", "uttar", "pradesh", "gujarat", "kerala", "rajasthan",
                 "west", "bengal", "andhra", "odisha", "punjab", "madhya", "bihar", "assam", "goa", "jharkhand"}
CITY_ALIAS = {"bangalore": "bengaluru", "gurgaon": "gurugram", "bombay": "mumbai", "madras": "chennai", "calcutta": "kolkata",
              "cochin": "kochi", "trivandrum": "thiruvananthapuram", "ncr": "delhi"}
_SENIORITY = {"sr": "senior", "jr": "junior"}
PRIORITY = {s.name: s.priority for s in config.SITES}


def company_tokens(name: str) -> tuple[str, ...]:
    text = re.sub(r"\([^)]*\)", " ", (name or "").lower().replace("&", " and "))
    return tuple(t for t in re.split(r"[^a-z0-9]+", text) if t and t not in LEGAL)


def same_company(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return long_[: len(short)] == short and len(short[0]) >= 3


def title_key(title: str) -> str:
    words = re.split(r"[^a-z0-9+#]+", (title or "").lower().replace("&", " and "))
    return " ".join(_SENIORITY.get(w, w) for w in words if w)


def cities(*places: str) -> frozenset[str]:
    found = set()
    for place in places:
        for part in re.split(r"[,/;|()\-]+", (place or "").lower()):
            for word in re.split(r"\s+", part.strip()):
                word = CITY_ALIAS.get(word, word)
                if word and word not in GENERIC_PLACE and len(word) > 2:
                    found.add(word)
    return frozenset(found)


def places_overlap(a: frozenset[str], b: frozenset[str]) -> bool:
    return not a or not b or bool(a & b)


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def group(jobs: list[dict]) -> list[list[dict]]:
    """Groups of jobs that are the same opening."""
    parent = list(range(len(jobs)))
    keyed = [(title_key(j["title"]), company_tokens(j["company"]), cities(j["location"], j.get("more_locations", ""))) for j in jobs]
    buckets: dict[str, list[int]] = {}
    by_url: dict[str, int] = {}
    for i, j in enumerate(jobs):
        buckets.setdefault(keyed[i][0], []).append(i)
        if j["url"] in by_url:
            parent[_find(parent, i)] = _find(parent, by_url[j["url"]])
        else:
            by_url[j["url"]] = i
    for idxs in buckets.values():
        for n, i in enumerate(idxs):
            for k in idxs[n + 1:]:
                if _find(parent, i) != _find(parent, k) and same_company(keyed[i][1], keyed[k][1]) and places_overlap(keyed[i][2], keyed[k][2]):
                    parent[_find(parent, i)] = _find(parent, k)
    groups: dict[int, list[dict]] = {}
    for i, j in enumerate(jobs):
        groups.setdefault(_find(parent, i), []).append(j)
    return list(groups.values())


def _first(members: list[dict], field: str):
    return next((m[field] for m in members if m.get(field) not in (None, "", [])), "")


def merge_group(members: list[dict]) -> dict:
    """One record for a group: each field comes from the richest site that has it."""
    members = sorted(members, key=lambda m: (PRIORITY.get(m["site"], 99), m["url"]))
    place = max(members, key=lambda m: (len(cities(m["location"], m.get("more_locations", ""))), -PRIORITY.get(m["site"], 99)))
    posted = [m["posted_date"] for m in members if isinstance(m.get("posted_date"), date)]
    seen = [m["first_seen"] for m in members if isinstance(m.get("first_seen"), date)]
    links, sites = [], []
    for m in members:
        if m["site"] not in sites:
            sites.append(m["site"])
        if (m["site"], m["url"]) not in links:
            links.append((m["site"], m["url"]))
    roles = []
    for m in members:
        for r in m.get("roles", []):
            if r not in roles:
                roles.append(r)
    return {
        "title": _first(members, "title"), "company": _first(members, "company"),
        "location": place["location"], "more_locations": place.get("more_locations", ""),
        "bengaluru": any(m["bengaluru"] for m in members), "remote": any(m["remote"] for m in members),
        "experience": _first(members, "experience"), "salary": _first(members, "salary"), "work_mode": _first(members, "work_mode"),
        "job_type": _first(members, "job_type"), "skills": _first(members, "skills"),
        "posted_date": min(posted) if posted else None, "first_seen": min(seen) if seen else None,
        "roles": roles, "sites": sites, "links": links, "url": links[0][1], "other_links": [u for _, u in links[1:]],
    }


def dedupe(jobs: list[dict]) -> list[dict]:
    return [merge_group(g) for g in group(jobs)]


def rank_key(job: dict):
    """Bengaluru first, then remote, then the rest of India; newest first inside each."""
    cls = 0 if job["bengaluru"] else 1 if job["remote"] else 2
    posted = job["posted_date"].toordinal() if job.get("posted_date") else 0
    return (cls, -posted, job["title"].lower())
