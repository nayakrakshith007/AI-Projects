"""The job-boards lane: V2's seven site workflows (Hirist, IIMJobs, Cutshort, Wellfound, Indeed, Naukri, LinkedIn) run from V3.

The code of the sites and their runner came with the V3 clone (identical to V2's): each site is its own process driving a visible Chrome with a saved
profile, slow and polite on purpose, and a human check is passed by the owner by hand, never solved or hidden here. This module
  1. starts them with the inherited runner (lanes, memory gate, stall restart, one retry) and reports each board live into the V3 run state,
  2. reads what each site saved in its workbook, and turns it into V3 jobs (location priority, source type 'Job board'),
so the boards flow through the same role routing, de-duplication, ranking, workbook and dashboard as every other source."""
import ctypes
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, places
from .readers.common import parse_date

BOARD_READER = "board_site"
MAX_AGE_DAYS = 60                      # board workbooks keep every job ever found; jobs first seen or posted longer ago than this are left out
LANE_STATUS = {"ok": "done", "finished with errors": "done", "needs you": "needs you", "stopped": "stopped"}      # anything else: failed


def keep_awake(on: bool) -> None:
    """While the boards run (a long job) the PC must not go to sleep."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))      # ES_CONTINUOUS [| ES_SYSTEM_REQUIRED]
    except Exception:
        pass


def convert(job: dict, src: dict) -> dict | None:
    """One job in V2's common format (pipeline/load.py) as a V3 job. None when the job is too old to matter."""
    posted, seen = job.get("posted_date"), job.get("first_seen")
    newest = max([d for d in (posted, seen) if isinstance(d, date)], default=None)
    if newest and (date.today() - newest) > timedelta(days=MAX_AGE_DAYS):
        return None
    place = (job.get("location") or "").strip()
    more = (job.get("more_locations") or "").strip()
    c = places.classify(place, more, bool(job.get("remote")))
    skills = job.get("skills") or ""
    return {
        "site": src["name"], "source_id": src["id"], "source_type": "Job board", "job_id": job["url"], "title": job["title"], "company": (job.get("company") or src["name"]).strip(),
        "location": place, "more_locations": more, "experience": job.get("experience") or "", "salary": job.get("salary") or "",
        "work_mode": job.get("work_mode") or ("Remote" if c["remote"] else ""), "skills": skills if isinstance(skills, str) else ", ".join(skills),
        "posted_date": parse_date(posted), "first_seen": None, "role_hint": job.get("role_hint") or "", "job_type": job.get("job_type") or "", "url": job["url"], **c,
    }


def status_for(result: dict) -> tuple[str, str]:
    """(V3 status, note) from one site result of the inherited runner."""
    status = LANE_STATUS.get(result["status"], "failed")
    parts = [result["status"]] if result["status"] not in ("ok",) else []
    parts += [p[:90] for p in result.get("problems", [])[:1]]
    if result.get("retried"):
        parts.append(f"second try after {result.get('first_status')}")
    return status, "; ".join(parts)


def run_boards(sources: list[dict], state, series: bool = False, run_sites=None, read_site=None, logs_dir: Path | None = None) -> dict[str, dict]:
    """Run the board sources and return {source id: {"status", "note", "seconds", "jobs", "read"}}.
    jobs is the list of V3 jobs read from the site's workbook (partial results count: a site that stopped on a human check keeps what it read);
    read is False when the workbook could not be read at all (the previous list is then kept by the caller)."""
    from pipeline import config as pc, load as pl, runner as pr
    run_sites = run_sites or pr.run_sites
    read_site = read_site or pl.read_site
    by_name = {s["slug"]: s for s in sources}
    sites = [pc.SITE_BY_NAME[n] for n in by_name if n in pc.SITE_BY_NAME]
    if not sites:
        return {}
    pc.activate_scope()
    lanes = pc.lanes_for(sites, series)
    logs_dir = logs_dir or config.OUTPUT_DIR / "logs" / f"boards_{datetime.now():%Y%m%d_%H%M}"
    out: dict[str, dict] = {}

    def on_start(name: str, log, rerun: int) -> None:
        state.source_started(by_name[name]["id"])
        state.source_update(by_name[name]["id"], note="restarted" if rerun else "")

    def on_done(res: dict) -> None:
        src = by_name.get(res["site"])
        if not src:
            return
        if res["status"].startswith("stuck"):                    # the runner starts a stuck site again at once
            state.source_update(src["id"], status="reading", note=res["status"])
            return
        status, note = status_for(res)
        out[src["id"]] = {"status": status, "note": note, "seconds": res["minutes"] * 60, "lane_status": res["status"]}
        state.source_done(src["id"], status, res.get("total") or 0, res["minutes"] * 60, note, new=res.get("new") or 0)

    keep_awake(True)
    try:
        run_sites(sites, lanes=lanes, on_done=on_done, logs_dir=logs_dir, on_start=on_start, control=None, on_note=state.add_event)
    finally:
        keep_awake(False)
    site_by_name = {s.name: s for s in sites}
    for name, src in by_name.items():
        rec = out.setdefault(src["id"], {"status": "failed", "note": "no result from the runner", "seconds": 0.0, "lane_status": "failed"})
        try:
            raw = read_site(site_by_name[name])
            jobs = [j for j in (convert(r, src) for r in raw) if j]
            rec.update(jobs=jobs, read=True, workbook_rows=len(raw))
        except Exception as e:                                    # a workbook that cannot be read must not stop the others
            rec.update(jobs=[], read=False, note=(rec["note"] + f"; workbook not readable: {type(e).__name__}").strip("; "))
    return out
