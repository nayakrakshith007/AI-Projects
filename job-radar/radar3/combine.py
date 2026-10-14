"""Combine the jobs of every source: drop what is not open to India, route to the ten roles, remove duplicates across sources, rank.

De-duplication reuses the V2 matching rules (pipeline/dedupe.py: same link, or same normalised title at the same company at an overlapping
place), so a job listed by RemoteOK and by its company's Greenhouse board becomes one row that names both sources."""
from pipeline.dedupe import group, merge_group

from . import roles

ELIGIBILITY_ORDER = {"yes": 0, "india": 1, "unclear": 2}


def rank_key(job: dict):
    """Remote open to India, then remote 'check eligibility', then Bengaluru, Hyderabad/Chennai, rest of India; newest first inside each."""
    posted = job["posted_date"].toordinal() if job.get("posted_date") else 0
    return (job["tier"], -posted, job["title"].lower())


def _merge(members: list[dict]) -> dict:
    job = merge_group(members)
    job["tier"] = min(m["tier"] for m in members)
    job["eligibility"] = min((m["eligibility"] for m in members), key=lambda e: ELIGIBILITY_ORDER.get(e, 9))
    job["source_types"] = sorted({m["source_type"] for m in members})
    job["source_ids"] = sorted({m["source_id"] for m in members})
    job["job_ids"] = [m["job_id"] for m in members]
    return job


def combine(jobs_by_source: dict[str, list[dict]], patterns: list[roles.RolePattern] | None = None) -> tuple[list[dict], list[dict], dict]:
    """Returns (matched, unmatched, stats). Jobs with tier None (not open to India) are counted, not kept."""
    patterns = patterns or roles.load_patterns()
    everything = [j for jobs in jobs_by_source.values() for j in jobs]
    open_to_india = [j for j in everything if j["tier"] is not None]
    for j in open_to_india:
        j["roles"] = roles.roles_for(j["title"], patterns)
    merged = [_merge(g) for g in group(open_to_india)]
    matched = sorted((j for j in merged if j["roles"]), key=rank_key)
    unmatched = sorted((j for j in merged if not j["roles"]), key=rank_key)
    tiers = {t: sum(1 for j in matched if j["tier"] == t) for t in range(5)}
    by_source: dict[str, int] = {}
    for j in matched:
        for sid in j["source_ids"]:
            by_source[sid] = by_source.get(sid, 0) + 1
    stats = {
        "read": {s: len(j) for s, j in jobs_by_source.items()}, "total_read": len(everything),
        "not_open_to_india": len(everything) - len(open_to_india), "unique": len(merged), "duplicates_removed": len(open_to_india) - len(merged),
        "matched": len(matched), "unmatched": len(unmatched), "tiers": tiers,
        "by_source": by_source,
        "remote_open_to_india": tiers[0], "remote_check_eligibility": tiers[1], "bengaluru": tiers[2], "hyderabad_chennai": tiers[3], "rest_of_india": tiers[4],
    }
    return matched, unmatched, stats
