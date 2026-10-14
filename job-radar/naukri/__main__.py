"""Command line:  python -m naukri search [--role NAME ...] [--hours N]   |   python -m naukri check

Reads job-radar-V3/input.csv (Role, Keywords, Experience, Location)."""
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from common.inputs import INPUT_FILE, load_input, queries_from
from common.window import read_latest, record_run, resolve_hours

from . import config, excel, notify, session
from . import search as search_mod


def main() -> None:
    ap = argparse.ArgumentParser(prog="naukri", description="Naukri workflow (real Chrome, saved session, polite paging)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="open Chrome so you can pass Naukri's human check by hand (once in a while)")
    s = sub.add_parser("search", help="read the newest jobs for the roles in input.csv into naukri/output/Naukri.xlsx")
    s.add_argument("--role", action="append", help="only this role from input.csv (repeatable); default all roles")
    s.add_argument("--hours", type=int, default=None, help="posted within this many hours; default: from midnight of the latest posted date already read (never less than 24 h, at most 30 days)")
    s.add_argument("--workers", type=int, default=config.WORKERS, help="searches read at the same time, in tabs of one Chrome (1-%d)" % config.WORKERS_MAX)
    s.add_argument("--input", default=str(INPUT_FILE), help="input CSV (default: job-radar-V3/input.csv)")
    args = ap.parse_args()

    if args.cmd == "check":
        print("Session saved." if session.wait_for_human() else "No results seen. Run it again.")
        return

    roles = load_input(Path(args.input))
    if args.role:
        wanted = {r.lower() for r in args.role}
        roles = [r for r in roles if r.role.lower() in wanted]
    if not roles:
        raise SystemExit("No matching roles in the input file")
    queries = queries_from(roles)
    hours, why = resolve_hours(args.hours, config.STATE_PATH, config.EXCEL_PATH, "Naukri")
    previous_latest = read_latest(config.STATE_PATH, config.EXCEL_PATH, "Naukri")
    print(f"{len(roles)} roles, {len(queries)} searches, window {why}", flush=True)
    saved = {"new": 0, "upd": 0, "total": 0, "locked": False}

    def save_batch(batch: list[dict]) -> None:
        """Save each search's jobs at once, so a run that is stopped part-way keeps everything read so far."""
        if saved["locked"]:
            return
        print("saving to Excel ...", flush=True)
        path, n_new, n_upd, total = excel.save(batch)
        if path.name != "Naukri.xlsx":      # Excel has the file open: stop saving piece by piece, save everything once at the end
            saved["locked"] = True
            path.unlink(missing_ok=True)
            return
        saved["new"] += n_new
        saved["upd"] += n_upd
        saved["total"] = total
        print(f"  saved, {total} rows in the workbook", flush=True)

    jobs, error = search_mod.search(
        queries, hours,
        on_page=lambda q, n, new: print(f"  [{q.role}] {q.keyword!r} in {q.location}, page {n}: {new} new jobs", flush=True),
        on_query_done=save_batch, workers=args.workers,
    )
    if jobs:  # raw backup of the whole run
        backup = config.RUNS_DIR / f"naukri_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(chr(10).join(
            json.dumps(j, ensure_ascii=False, default=lambda o: o.isoformat() if isinstance(o, date) else str(o)) for j in jobs
        ), encoding="utf-8")
        if saved["locked"] or not saved["total"]:
            print("saving to Excel ...", flush=True)
            path, n_new, n_upd, total = excel.save(jobs)
        else:
            path, n_new, n_upd, total = config.EXCEL_PATH, saved["new"], saved["upd"], saved["total"]
        print(f"{len(jobs)} jobs read: {n_new} new, {n_upd} already known. {total} in {path.name}")
        if path.name == "Naukri.xlsx":
            record_run(config.STATE_PATH, jobs, error, previous_latest)
        if path.name != "Naukri.xlsx":
            print("!! Naukri.xlsx is open in Excel; wrote a timestamped copy instead. Close Excel and rerun.")
    else:
        print("No jobs read.")
    if error:
        print("!!", error)
        if "human check" in error:
            notify.popup("Job Radar: Naukri needs you", "Naukri is asking for the human check.\nDouble-click check.bat, tick the box, then rerun.")


main()
