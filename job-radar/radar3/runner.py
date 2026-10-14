"""Run the due sources side by side (plain HTTP, no browser), keep each source's last good jobs, then build the workbook.

- Each source writes radar3/output/sources/<id>.json. A source that fails keeps its previous file, so one outage never empties the workbook.
- Canary: a source that returns 0 jobs twice in a row is 'broken'; 0 once is 'empty' (watch it); an error is 'failed'.
- Only one run at a time (a lock file with the process id; a stale lock from a dead process is ignored)."""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

from . import config, places
from .boards import BOARD_READER, run_boards
from .build import build
from .fsutil import safe_replace
from .http import Http
from .readers import READERS
from .sources import load_sources, select
from .state import RunState

class AlreadyRunning(RuntimeError):
    pass


def _pid_alive(pid: int) -> bool:
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return bool(ok) and code.value == 259                                  # STILL_ACTIVE


def acquire_lock(path: Path | None = None) -> None:
    path = path or config.OUTPUT_DIR / "run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                pid = int(path.read_text().strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and _pid_alive(pid):
                raise AlreadyRunning(f"a run is already going (process {pid})")
            path.unlink(missing_ok=True)
    raise AlreadyRunning("could not take the run lock")


def release_lock(path: Path | None = None) -> None:
    (path or config.OUTPUT_DIR / "run.lock").unlink(missing_ok=True)


def _jsonable(job: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in job.items()}


def save_source_jobs(sid: str, jobs: list[dict], out_dir: Path = config.SOURCES_OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f"{sid}.json.tmp"
    tmp.write_text(json.dumps([_jsonable(j) for j in jobs]), encoding="utf-8")
    safe_replace(tmp, out_dir / f"{sid}.json")


def load_source_jobs(sid: str, out_dir: Path = config.SOURCES_OUT) -> list[dict]:
    path = out_dir / f"{sid}.json"
    if not path.exists():
        return []
    jobs = json.loads(path.read_text(encoding="utf-8"))
    for j in jobs:
        j["posted_date"] = date.fromisoformat(j["posted_date"]) if j.get("posted_date") else None
        j["first_seen"] = None
        if not re.match(r"(\d+|multiple) locations?", j["location"], re.I):      # Workday's '2 Locations' was flagged at read time and stays so
            j.update(places.classify(j["location"], j.get("more_locations", ""), j.get("remote", False)))     # rule changes apply without reading the sites again
    return jobs


def load_stats(path: Path | None = None) -> dict:
    path = path or config.SOURCE_STATS_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_stats(stats: dict, path: Path | None = None) -> None:
    path = path or config.SOURCE_STATS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(stats, indent=1), encoding="utf-8")
    safe_replace(tmp, path)


def read_source(src: dict, http) -> tuple[list[dict], float]:
    """Read one source; an error is retried once after a short wait (a passing network or server hiccup should not cost a day)."""
    t0 = time.monotonic()
    for attempt in range(config.SOURCE_RETRIES + 1):
        try:
            return READERS[src["reader"]](src, http), time.monotonic() - t0
        except Exception:
            if attempt >= config.SOURCE_RETRIES:
                raise
            time.sleep(config.RETRY_WAIT_SEC)
    raise RuntimeError("unreachable")


def quality(jobs: list[dict]) -> dict:
    """Shares of jobs with a missing place, and of repeated links: a page redesign often shows up here before the count changes."""
    n = len(jobs) or 1
    return {"no_place": sum(1 for j in jobs if not j.get("location")) / n, "duplicate_links": 1 - len({j["url"] for j in jobs}) / n}


def judge(prev: dict, jobs: list[dict], today: date) -> tuple[str, dict, str, bool]:
    """The health check of one read. Returns (status, new stats entry, note, keep).
    empty: 0 jobs once (watch); broken: 0 twice in a row. shrunk: far fewer jobs than usual (below 30%: the previous list is kept, as the read was
    probably partial). degraded: more than half of the jobs have no place, which usually means the page layout changed. done: everything normal."""
    entry, count = dict(prev), len(jobs)
    if count == 0:
        entry["zero_runs"] = prev.get("zero_runs", 0) + 1
        if entry["zero_runs"] >= 2:
            return "broken", entry, "returned nothing twice in a row: the page or API changed; re-read it with the browser tools", False
        return "empty", entry, "returned nothing (watch)", False
    counts = list(prev.get("counts") or ([prev["last_count"]] if prev.get("last_count") else []))
    usual = sorted(counts[-5:])[len(counts[-5:]) // 2] if counts else 0
    status, note, keep = "done", "", True
    if usual >= config.MIN_COUNT_FOR_SHRINK and count < usual * config.SHRINK_KEEP_BELOW:
        entry["zero_runs"] = 0
        return "shrunk", entry, f"returned {count}, usually about {usual}: kept the previous list", False
    if usual >= config.MIN_COUNT_FOR_SHRINK and count < usual * config.SHRINK_FLAG_BELOW:
        status, note = "shrunk", f"returned {count}, usually about {usual}"
    q = quality(jobs)
    if count >= 10 and q["no_place"] > 0.5:
        status, note = "degraded", f"{q['no_place']:.0%} of the jobs have no place: the layout may have changed"
    entry.update(zero_runs=0, last_ok=today.isoformat(), last_count=count, counts=(counts + [count])[-10:])
    return status, entry, note, keep


def health_report(sources: list[dict], stats: dict, today: date | None = None) -> list[dict]:
    """One row per enabled source for `python -m radar3 health`: last good read, count trend, and a 'stale' flag when it has not worked for too long."""
    today, rows = today or date.today(), []
    for s in sources:
        if s.get("enabled") != "yes":
            continue
        st = stats.get(s["id"], {})
        last = st.get("last_ok")
        age = (today - date.fromisoformat(last)).days if last else None
        limit = 3 if s["schedule"] == "daily" else 10
        flag = "never read" if age is None else "stale" if age > limit else "zero runs" if st.get("zero_runs") else ""
        rows.append({"id": s["id"], "name": s["name"], "schedule": s["schedule"], "last_ok": last, "age_days": age, "last_count": st.get("last_count"),
                     "counts": st.get("counts", []), "zero_runs": st.get("zero_runs", 0), "flag": flag})
    return rows


def _build_all(all_sources: list[dict], out_dir: Path, excel_path: Path, today: date) -> tuple[Path, dict]:
    """Combine every enabled source's last good jobs into the workbook and the dashboard snapshot."""
    jobs_by_source = {s["name"] + f" ({s['id']})": load_source_jobs(s["id"], out_dir) for s in all_sources if s.get("enabled") == "yes"}
    jobs_by_source = {k: v for k, v in jobs_by_source.items() if v}
    return build(jobs_by_source, path=excel_path, snapshot_path=config.SNAPSHOT_PATH if excel_path == config.EXCEL_PATH else None, today=today)


def _apply_board_results(board_due: list[dict], box: dict, stats: dict, results: dict, state: RunState, out_dir: Path, today: date) -> None:
    """Judge what the job boards delivered like any other source. A board that stopped on a human check keeps what it read ('needs you');
    a board that failed, or whose workbook could not be read, keeps its previous list."""
    res = box.get("res") or {}
    for src in board_due:
        sid = src["id"]
        rec = res.get(sid) or {"status": "failed", "note": box.get("error", "the boards lane did not finish"), "seconds": 0.0, "jobs": [], "read": False}
        lane, jobs, note = rec["status"], rec.get("jobs") or [], rec.get("note", "")
        status = lane
        if rec.get("read") and lane in ("done", "needs you"):
            judged, stats[sid], jnote, keep = judge(stats.get(sid, {}), jobs, today)
            if keep and jobs:
                save_source_jobs(sid, jobs, out_dir)
            if lane == "done":
                status, note = judged, (jnote or note)
            else:
                note = (note + "; " + jnote).strip("; ")
        results[sid] = {"status": status, "jobs": len(jobs), "seconds": round(rec.get("seconds", 0.0), 1), "note": note}
        state.source_update(sid, status=status, jobs=len(jobs), note=note)


def run(mode: str = "auto", only: list[str] | None = None, http=None, today: date | None = None, state: RunState | None = None,
        workers: int = config.HTTP_WORKERS, started_by: str = "command line", sources: list[dict] | None = None,
        out_dir: Path = config.SOURCES_OUT, excel_path: Path = config.EXCEL_PATH, use_lock: bool = True,
        boards: bool = True, board_runner=None, board_reader=None) -> dict:
    """Read the due sources. The fast sources (plain requests) and the job boards (V2's site workflows: visible Chrome, slow, polite) run side by side;
    the workbook is built when the fast sources are done and again when the boards finish. boards=False leaves the job boards out."""
    today = today or date.today()
    http = http or Http()
    state = state or RunState()
    all_sources = sources if sources is not None else load_sources()
    stats = load_stats()
    due = select(all_sources, mode, stats, today, only)
    http_due = [s for s in due if s["reader"] != BOARD_READER]
    board_due = [s for s in due if s["reader"] == BOARD_READER] if boards else []
    due = http_due + board_due
    if use_lock:
        acquire_lock()
    t_run = time.monotonic()
    try:
        state.begin(due, mode if not only else "selected", started_by)
        results: dict[str, dict] = {}
        box: dict = {}
        board_thread = None
        if board_due:
            def go() -> None:
                try:
                    box["res"] = run_boards(board_due, state, run_sites=board_runner, read_site=board_reader)
                except BaseException as e:                                  # the boards lane must never take the whole run down
                    box["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            board_thread = threading.Thread(target=go, name="boards", daemon=True)
            board_thread.start()

        def work(src: dict):
            state.source_started(src["id"])
            return read_source(src, http)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futures = {ex.submit(work, s): s for s in http_due}
            for fut in as_completed(futures):
                src = futures[fut]
                try:
                    jobs, secs = fut.result()
                except Exception as e:                                   # a failed source keeps its previous jobs
                    status, secs, jobs, note = "failed", 0.0, None, f"{type(e).__name__}: {str(e)[:120]}"
                else:
                    status, stats[src["id"]], note, keep = judge(stats.get(src["id"], {}), jobs, today)
                    if keep and jobs:
                        save_source_jobs(src["id"], jobs, out_dir)
                results[src["id"]] = {"status": status, "jobs": len(jobs or []), "seconds": round(secs, 1), "note": note}
                state.source_done(src["id"], status, len(jobs or []), secs, note)
        save_stats(stats)
        if board_thread:                                                     # fast sources are in: show them now, the boards need much longer
            state.phase("building", "fast sources done; updating the workbook while the job boards keep reading")
            _build_all(all_sources, out_dir, excel_path, today)
            state.phase("reading", "workbook updated; waiting for the job boards")
            board_thread.join()
            _apply_board_results(board_due, box, stats, results, state, out_dir, today)
            save_stats(stats)
        config.HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.HEALTH_PATH.write_text(json.dumps({"date": today.isoformat(), "sources": health_report(all_sources, stats, today)}, indent=1), encoding="utf-8")

        state.phase("building", "combining the sources and writing the workbook")
        written, build_stats = _build_all(all_sources, out_dir, excel_path, today)
        summary = {"finished": datetime.now().isoformat(timespec="seconds"), "seconds": round(time.monotonic() - t_run, 1), "mode": "selected" if only else mode,
                   "sources_run": len(due), "ok": sum(r["status"] == "done" for r in results.values()),
                   "problems": {sid: r for sid, r in results.items() if r["status"] != "done"}, "workbook": str(written), "build": build_stats}
        for sid, r in results.items():                              # each source's last result, so a problem stays visible after a re-run of other sources
            stats.setdefault(sid, {}).update(last_status=r["status"], last_note=r["note"], last_run=today.isoformat(), last_seconds=r["seconds"], last_jobs=r["jobs"])
        for s in all_sources:                                       # how many role-matching jobs each source delivered in this build
            if s.get("enabled") == "yes":
                stats.setdefault(s["id"], {})["matched"] = build_stats.get("by_source", {}).get(s["id"], 0)
        save_stats(stats)
        if excel_path == config.EXCEL_PATH:
            try:
                from .dashboard import build_dashboard
                build_dashboard()
            except Exception as e:                                       # the dashboard must never break a run
                summary["dashboard_error"] = f"{type(e).__name__}: {str(e)[:100]}"
        state.finish(summary)
        _history(results, today, due)
        if excel_path == config.EXCEL_PATH:                          # only real runs; tests write to their own folders
            _run_log(summary, state.data.get("started_by", ""), state.data.get("started", ""))
        config.LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
        if excel_path == config.EXCEL_PATH:
            config.LAST_RUN_PATH.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
        return summary
    finally:
        if use_lock:
            release_lock()


def _run_log(summary: dict, started_by: str, started: str) -> None:
    """One line per finished run: when, how long, who started it, how many sources were ok, matched jobs and new jobs."""
    b = summary["build"]
    config.RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.RUNS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"started": started, "finished": summary["finished"], "seconds": summary["seconds"], "mode": summary["mode"], "started_by": started_by,
                            "sources_run": summary["sources_run"], "ok": summary["ok"], "problems": len(summary["problems"]), "matched": b["matched"],
                            "new_today": b["new_today"], "remote_open_to_india": b["remote_open_to_india"]}) + chr(10))


def _history(results: dict, today: date, due: list[dict]) -> None:
    by_id = {s["id"]: s for s in due}
    config.HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.HISTORY_PATH, "a", encoding="utf-8") as f:
        for sid, r in results.items():
            f.write(json.dumps({"date": today.isoformat(), "source": sid, "name": by_id[sid]["name"], **r}) + "\n")
