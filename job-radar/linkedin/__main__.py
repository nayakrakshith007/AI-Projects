"""Command line:  python -m linkedin search [--role NAME ...] [--hours N] [--engine jobspy|browser]   |   python -m linkedin check

Reads job-radar-V3/input.csv (Role, Keywords, Experience, Location)."""
import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path

from common.inputs import INPUT_FILE, load_input, queries_from
from common.window import read_latest, record_run, resolve_hours

from . import config, excel, notify


def main() -> None:
    ap = argparse.ArgumentParser(prog="linkedin", description="LinkedIn workflow (public job data, no login, paced and parallel)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="browser engine only: open Chrome so you can handle a LinkedIn wall by hand (do not sign in)")
    s = sub.add_parser("search", help="read the newest jobs for the roles in input.csv into linkedin/output/LinkedIn.xlsx")
    s.add_argument("--role", action="append", help="only this role from input.csv (repeatable); default all roles")
    s.add_argument("--hours", type=int, default=None, help="posted within this many hours; default: from midnight of the latest posted date already read (never less than 24 h, at most 30 days)")
    s.add_argument("--input", default=str(INPUT_FILE), help="input CSV (default: job-radar-V3/input.csv)")
    s.add_argument("--engine", choices=["jobspy", "browser"], default="jobspy", help="jobspy: paced and parallel (default); browser: real Chrome fallback")
    s.add_argument("--workers", type=int, default=config.WORKERS, help="searches run in parallel (jobspy engine)")
    args = ap.parse_args()

    if args.cmd == "check":
        from . import session
        print("Done." if session.wait_for_human() else "No results seen. Run it again.")
        return

    roles = load_input(Path(args.input))
    if args.role:
        wanted = {r.lower() for r in args.role}
        roles = [r for r in roles if r.role.lower() in wanted]
    if not roles:
        raise SystemExit("No matching roles in the input file")
    queries = queries_from(roles)
    hours, why = resolve_hours(args.hours, config.STATE_PATH, config.EXCEL_PATH, "LinkedIn")
    previous_latest = read_latest(config.STATE_PATH, config.EXCEL_PATH, "LinkedIn")
    started = time.time()
    print(f"{len(roles)} roles, {len(queries)} searches, window {why}, engine {args.engine}", flush=True)
    saved = {"new": 0, "upd": 0, "total": 0, "locked": False}

    def save_batch(batch: list[dict]) -> None:
        """Save each search's jobs as soon as it ends, so a run that is stopped part-way keeps everything read so far."""
        if saved["locked"]:
            return
        print("saving to Excel ...", flush=True)
        path, n_new, n_upd, total = excel.save(batch)
        if path.name != "LinkedIn.xlsx":      # Excel has the file open: stop saving piece by piece, save everything once at the end
            saved["locked"] = True
            path.unlink(missing_ok=True)
            return
        saved["new"] += n_new
        saved["upd"] += n_upd
        saved["total"] = total
        print(f"  saved, {total} rows in the workbook", flush=True)

    if args.engine == "jobspy":
        from . import engine_jobspy
        jobs, error = engine_jobspy.search(
            queries, hours, workers=args.workers, on_query_done=save_batch,
            on_batch=lambda q, off, n, new: print(f"  [{q.role}] {q.keyword!r} offset {off}: {n} jobs, {new} new", flush=True),
        )
    else:
        from . import search as browser_engine
        jobs, error = browser_engine.search(
            queries, hours, on_round=lambda q, c: print(f"  [{q.role}] {q.keyword!r}: {c} cards loaded", flush=True)
        )
    print(f"read {len(jobs)} jobs in {round((time.time() - started) / 60, 1)} min")
    if jobs:  # raw backup first, so a failure while writing Excel never loses a run
        backup = config.RUNS_DIR / f"linkedin_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(chr(10).join(
            json.dumps(j, ensure_ascii=False, default=lambda o: o.isoformat() if isinstance(o, date) else str(o)) for j in jobs
        ), encoding="utf-8")
        if saved["locked"] or not saved["total"]:
            print("saving to Excel ...", flush=True)
            path, n_new, n_upd, total = excel.save(jobs)
        else:
            path, n_new, n_upd, total = config.EXCEL_PATH, saved["new"], saved["upd"], saved["total"]
        print(f"{n_new} new, {n_upd} already known. {total} in {path.name}")
        if path.name == "LinkedIn.xlsx":
            record_run(config.STATE_PATH, jobs, error, previous_latest)
        if path.name != "LinkedIn.xlsx":
            print("!! LinkedIn.xlsx is open in Excel; wrote a timestamped copy instead. Close Excel and rerun.")
    else:
        print("No jobs read.")
    if error:
        print("!!", error)
        if "rate limit" in error or "wall" in error:
            notify.popup("Job Radar: LinkedIn stopped", "LinkedIn pushed back or showed a wall.\nPartial results were saved. Rerun later, or try --engine browser.")


main()
