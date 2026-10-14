"""The history of every run: one line per site per run (and one per run) in pipeline/output/history.jsonl, and the numbers the Performance
tab shows (duration spread, reliability, yield, parallel efficiency).

Read the numbers with care: a site's duration depends on the time window (24 h or 7 days of postings) and on the role scope (8 tech roles or
all 15), so the summary can filter by scope and by status. Runs that were stopped by hand are kept in the history but left out of timing and
reliability, because they say nothing about the site."""
import json
import re
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from . import config

HISTORY_PATH = config.OUTPUT_DIR / "history.jsonl"
EXPERIMENTS_PATH = config.HERE / "experiments.json"
TECH_ONLY_SITES = {"hirist", "iimjobs", "cutshort", "wellfound"}      # these sites only ever read the tech roles
GOOD = ("ok", "finished with errors")
# How the runs of 2026-10-12 before the history existed were started (read from the run folders' names and my notes of that day):
# "parallel" = every site at once (the first design, which ran out of memory), "series" = one site at a time, "lanes" = the four lanes.
MODE_BY_RUN = {"2026-10-12_0002": "parallel", "2026-10-12_0901": "parallel", "2026-10-12_0933": "series", "2026-10-12_1044": "series",
               "2026-10-12_1325": "lanes", "2026-10-12_1356": "lanes", "2026-10-12_1819": "lanes", "2026-10-12_1826": "lanes"}
# Durations printed by the run itself, where the log only lets me estimate from the folder name (the folder name has no seconds).
KNOWN_MINUTES = {("2026-10-12_0002", "cutshort"): 1.1, ("2026-10-12_0002", "hirist"): 1.9, ("2026-10-12_0002", "iimjobs"): 2.7}
HEADER_ROLES = re.compile(r"(\d+) roles")
HEADER_WINDOW = re.compile(r"window (\d+) h")
HEADER_TOTAL = re.compile(r"(\d+) (?:searches|[A-Za-z]+ lists|Wellfound page lists)")
NEW_LINE = re.compile(r"(\d+) new, (\d+) already known\.\s+(\d+) in (\S+)")
READ_LINE = re.compile(r"read (\d+) jobs in ([\d.]+) min")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def parse_header(text: str, site: str) -> dict:
    """Roles, planned searches and window hours from the first lines of a site log."""
    head = "\n".join(text.splitlines()[:4])
    roles = HEADER_ROLES.search(head)
    window = HEADER_WINDOW.search(head)
    total = HEADER_TOTAL.search(head) or re.search(r"(\d+) [\w ]*lists", head)
    n_roles = int(roles.group(1)) if roles else None
    if n_roles is not None:
        scope = "all" if n_roles > 8 else "tech"
    else:
        scope = "tech" if site in TECH_ONLY_SITES else "unknown"
    return {"roles": n_roles, "searches_total": int(total.group(1)) if total else None,
            "window_hours": int(window.group(1)) if window else None, "scope": scope}


def read_records(path: Path | None = None) -> list[dict]:
    path = path or HISTORY_PATH
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def known_runs(path: Path | None = None) -> set[str]:
    return {r["run_id"] for r in read_records(path) if r.get("type") == "run"}


def _append(records: list[dict], path: Path | None = None) -> None:
    path = path or HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _iso_to_ts(value: str | None) -> float | None:
    try:
        return datetime.fromisoformat(value).timestamp() if value else None
    except ValueError:
        return None


def record_from_state(data: dict, path: Path | None = None, source: str = "live") -> bool:
    """Write the history lines of a run from its run_state.json data. False when this run is already in the history."""
    run_id = Path(data.get("run_dir") or data.get("started", "")).name or data.get("started", "")
    if run_id in known_runs(path):
        return False
    scope = data.get("scope") or "tech"
    mode = "series" if data.get("series") else "lanes"
    recs, ok, new_sum = [], 0, 0
    for name, s in data.get("sites", {}).items():
        if s.get("status") in ("waiting",):
            continue
        header = {}
        if s.get("log") and Path(s["log"]).exists():
            header = parse_header(Path(s["log"]).read_text(encoding="utf-8", errors="replace"), name)
        started, finished = _iso_to_ts(s.get("started")), _iso_to_ts(s.get("finished"))
        minutes = s.get("minutes")
        if minutes is None and started and finished:
            minutes = round((finished - started) / 60, 1)
        recs.append({"type": "site", "run_id": run_id, "site": name, "started": s.get("started"), "finished": s.get("finished"),
                     "minutes": minutes, "status": s.get("status"), "new": s.get("new"), "known": s.get("known"), "total": s.get("total"),
                     "reruns": s.get("reruns", 0), "problems": len(s.get("problems") or []), "searches_total": header.get("searches_total"),
                     "roles": header.get("roles"), "window_hours": header.get("window_hours"), "scope": header.get("scope") or scope,
                     "lane": s.get("lane"), "mode": mode, "source": source, "complete": s.get("status") in GOOD + ("needs you", "failed", "timed out", "stalled")})
        ok += s.get("status") == "ok"
        new_sum += s.get("new") or 0
    started, finished = _iso_to_ts(data.get("started")), _iso_to_ts(data.get("finished"))
    build_s = None
    for e in data.get("events", []):
        if "building" in e["text"] and finished:
            t = _iso_to_ts(e["t"])
            build_s = round(finished - t) if t else None
    stats = data.get("stats") or {}
    recs.append({"type": "run", "run_id": run_id, "started": data.get("started"), "finished": data.get("finished"),
                 "wall_minutes": round((finished - started) / 60, 1) if started and finished else None,
                 "scope": scope, "series": bool(data.get("series")), "mode": mode, "phase": data.get("phase"), "sites": len(recs), "sites_ok": ok,
                 "new_sum": new_sum, "build_seconds": build_s, "resources": data.get("resources"), "source": source,
                 "stats": {k: stats.get(k) for k in ("new_today", "new_today_bengaluru", "matched", "bengaluru", "duplicates_removed", "unmatched", "parked_non_tech")} if stats else None})
    _append(recs, path)
    return True


# ---------------------------------------------------------------- backfill from the logs of earlier runs
def _report(text: str) -> dict | None:
    status = re.search(r"^# (\w+): (.+)$", text, re.M)
    fin = re.search(r"Finished: (\S+ \S+), took ([\d.]+) min", text)
    jobs = re.search(r"Jobs: (\d+) new, (\d+) already known, (\d+) jobs", text)
    att = re.search(r"Attempts: (\d+)", text)
    if not (status and fin):
        return None
    return {"status": status.group(2).strip(), "finished": fin.group(1).replace(" ", "T"), "minutes": float(fin.group(2)),
            "new": int(jobs.group(1)) if jobs else None, "known": int(jobs.group(2)) if jobs else None,
            "total": int(jobs.group(3)) if jobs else None, "attempts": int(att.group(1)) if att else 1,
            "problems": len(re.findall(r"^- !!", text, re.M))}


def backfill(logs_dir: Path | None = None, path: Path | None = None) -> int:
    """Turn the logs and reports of earlier runs into history lines. Returns how many runs were added."""
    logs_dir = logs_dir or config.LOGS_DIR
    added = 0
    for run in sorted(p for p in logs_dir.iterdir() if p.is_dir()) if logs_dir.exists() else []:
        if run.name in known_runs(path):
            continue
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})", run.name)
        if not m:
            continue
        run_start = datetime(*[int(x) for x in m.groups()])
        recs, ok, new_sum = [], 0, 0
        for log in sorted(run.glob("*.log")):
            if log.name == "errors.log" or "_rerun" in log.name:
                continue
            site = log.stem
            text = log.read_text(encoding="utf-8", errors="replace")
            header = parse_header(text, site)
            rep_file = run / f"{site}_report.md"
            rep = _report(rep_file.read_text(encoding="utf-8")) if rep_file.exists() else None
            mtime = datetime.fromtimestamp(log.stat().st_mtime)
            if rep:
                finished = datetime.fromisoformat(rep["finished"])
                minutes, status, new, known, total, problems = rep["minutes"], rep["status"], rep["new"], rep["known"], rep["total"], rep["problems"]
                source, reruns = "report", rep["attempts"] - 1
            else:
                nl = None
                for line in reversed(text.splitlines()):
                    nl = NEW_LINE.search(line)
                    if nl:
                        break
                rl = READ_LINE.search(text)
                finished = mtime
                if nl:
                    new, known, total = int(nl.group(1)), int(nl.group(2)), int(nl.group(3))
                    status = "ok" if "!!" not in text else "finished with errors"
                    minutes = float(rl.group(2)) if rl else round((mtime - run_start).total_seconds() / 60, 1)
                    problems = text.count("\n!!")
                    source = "log"
                else:
                    new = known = total = None
                    status = "stopped"                  # no summary line: the run was ended by hand before this site finished
                    minutes = round((mtime - run_start).total_seconds() / 60, 1)
                    problems, source = 0, "log"
                reruns = 0
            minutes = KNOWN_MINUTES.get((run.name, site), minutes)
            started = finished - timedelta(minutes=minutes or 0)
            recs.append({"type": "site", "run_id": run.name, "site": site, "started": started.isoformat(timespec="seconds"),
                         "finished": finished.isoformat(timespec="seconds"), "minutes": minutes, "status": status, "new": new,
                         "known": known, "total": total, "reruns": reruns, "problems": problems,
                         "searches_total": header["searches_total"], "roles": header["roles"], "window_hours": header["window_hours"],
                         "scope": header["scope"], "lane": None, "mode": MODE_BY_RUN.get(run.name, "lanes"), "source": source, "complete": status != "stopped"})
            ok += status == "ok"
            new_sum += new or 0
        if not recs:
            continue
        begin = min(datetime.fromisoformat(r["started"]) for r in recs)
        end = max(datetime.fromisoformat(r["finished"]) for r in recs)
        scopes = {r["scope"] for r in recs if r["scope"] != "unknown"}
        recs.append({"type": "run", "run_id": run.name, "started": begin.isoformat(timespec="seconds"), "finished": end.isoformat(timespec="seconds"),
                     "wall_minutes": round((end - begin).total_seconds() / 60, 1), "scope": "all" if "all" in scopes else "tech",
                     "series": MODE_BY_RUN.get(run.name) == "series", "mode": MODE_BY_RUN.get(run.name, "lanes"),
                     "phase": "finished" if all(r["complete"] for r in recs) else "stopped", "sites": len(recs), "sites_ok": ok,
                     "new_sum": new_sum, "build_seconds": None, "resources": None, "stats": None, "source": "backfill"})
        _append(recs, path)
        added += 1
    return added


# ---------------------------------------------------------------- the numbers
def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def summary(records: list[dict], scope: str = "any", only_ok: bool = False, mode: str = "any") -> dict:
    sites = [r for r in records if r.get("type") == "site"]
    runs = [r for r in records if r.get("type") == "run"]
    if scope != "any":
        sites = [r for r in sites if r.get("scope") == scope]
        runs = [r for r in runs if r.get("scope") == scope]
    if mode != "any":
        sites = [r for r in sites if r.get("mode") == mode]
        runs = [r for r in runs if r.get("mode") == mode]
    counted = [r for r in sites if r.get("status") != "stopped"]          # a hand-stopped site tells nothing about the site
    per_site = {}
    for name in sorted({r["site"] for r in counted}):
        rows = sorted((r for r in counted if r["site"] == name), key=lambda r: r.get("started") or "")
        good = [r for r in rows if r["status"] in GOOD and r.get("minutes") is not None]
        used = good if only_ok else rows
        mins = [r["minutes"] for r in used if r.get("minutes") is not None and r["status"] in GOOD]
        news = [r["new"] for r in good if r.get("new") is not None]
        rate = [r["new"] / r["minutes"] for r in good if r.get("new") is not None and r.get("minutes")]
        per_site[name] = {
            "runs": len(rows), "ok": sum(r["status"] == "ok" for r in rows), "good": len(good),
            "success_rate": round(100 * sum(r["status"] == "ok" for r in rows) / len(rows)) if rows else None,
            "median_min": round(statistics.median(mins), 1) if mins else None, "fastest_min": min(mins) if mins else None,
            "slowest_min": max(mins) if mins else None, "p90_min": round(_pct(mins, .9), 1) if mins else None,
            "last_min": rows[-1].get("minutes"), "last_status": rows[-1]["status"], "last_started": rows[-1].get("started"),
            "avg_new": round(statistics.mean(news), 1) if news else None, "total_new": sum(news),
            "new_per_min": round(statistics.median(rate), 1) if rate else None,
            "restarts": sum(r.get("reruns") or 0 for r in rows), "problems": sum(r.get("problems") or 0 for r in rows),
            "trend": [r["minutes"] for r in good][-12:],
        }
    run_rows = []
    for r in sorted(runs, key=lambda r: r.get("started") or "", reverse=True):
        mine = [s for s in sites if s["run_id"] == r["run_id"]]
        busy = round(sum(s.get("minutes") or 0 for s in mine), 1)
        wall = r.get("wall_minutes")
        run_rows.append({**r, "busy_minutes": busy, "parallel_efficiency": round(busy / wall, 2) if wall else None,
                         "slowest_site": max(mine, key=lambda s: s.get("minutes") or 0)["site"] if mine else None,
                         "site_rows": [{k: s.get(k) for k in ("site", "started", "finished", "minutes", "status", "new", "total", "reruns", "scope", "window_hours", "searches_total", "source")}
                                       for s in sorted(mine, key=lambda s: s.get("started") or "")]})
    done = [r for r in run_rows if r.get("phase") == "finished" and r.get("wall_minutes")]
    return {"per_site": per_site, "runs": run_rows[:60], "insights": insights(per_site, done), "scope": scope, "mode": mode, "only_ok": only_ok,
            "totals": {"site_runs": len(counted), "runs": len(run_rows), "complete_runs": len(done),
                       "new_jobs": sum(r.get("new") or 0 for r in counted if r["status"] in GOOD),
                       "median_wall_min": round(statistics.median([r["wall_minutes"] for r in done]), 1) if done else None}}


def insights(per_site: dict, done_runs: list[dict]) -> list[str]:
    out = []
    timed = {n: s for n, s in per_site.items() if s["median_min"] is not None}
    if timed:
        slow = max(timed, key=lambda n: timed[n]["median_min"])
        total = sum(s["median_min"] for s in timed.values())
        out.append(f"{slow} is the slowest site (median {timed[slow]['median_min']} min, {round(100 * timed[slow]['median_min'] / total)}% of all site time): it sets how long a full run takes.")
        fast = min(timed, key=lambda n: timed[n]["median_min"])
        out.append(f"{fast} is the fastest (median {timed[fast]['median_min']} min).")
    rated = {n: s for n, s in per_site.items() if s["new_per_min"] is not None}
    if rated:
        best = max(rated, key=lambda n: rated[n]["new_per_min"])
        worst = min(rated, key=lambda n: rated[n]["new_per_min"])
        out.append(f"Yield per minute: {best} adds the most new jobs per minute ({rated[best]['new_per_min']}); {worst} the fewest ({rated[worst]['new_per_min']}).")
    shaky = [n for n, s in per_site.items() if s["runs"] >= 2 and s["success_rate"] is not None and s["success_rate"] < 100]
    if shaky:
        out.append("Not always clean: " + ", ".join(f"{n} ({per_site[n]['success_rate']}% ok over {per_site[n]['runs']} runs)" for n in shaky) + ".")
    restarted = [n for n, s in per_site.items() if s["restarts"]]
    if restarted:
        out.append("Restarts after silence: " + ", ".join(f"{n} ({per_site[n]['restarts']})" for n in restarted) + ".")
    eff = [r for r in done_runs if r.get("parallel_efficiency")]
    if eff:
        e = eff[0]
        out.append(f"Latest complete run: {e['wall_minutes']} min wall time for {e['busy_minutes']} min of site work, i.e. {e['parallel_efficiency']}x parallelism (1.0x would be one site at a time).")
    if not out:
        out.append("Not enough history yet: complete a few runs and this fills in.")
    return out


def experiments() -> list[dict]:
    try:
        return json.loads(EXPERIMENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
