"""Command line:  python -m indeed search [--role NAME ...] [--hours N] [--workers N]

Reads job-radar-V3/input.csv (Role, Keywords, Experience, Location)."""
import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path

from common.inputs import INPUT_FILE, load_input, queries_from
from common.window import read_latest, record_run, resolve_hours

from . import config, engine, excel, notify


def main() -> None:
    ap = argparse.ArgumentParser(prog="indeed", description="Indeed workflow (JobSpy, parallel paced searches, no login)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="read the newest jobs for the roles in input.csv into indeed/output/Indeed.xlsx")
    s.add_argument("--role", action="append", help="only this role from input.csv (repeatable); default all roles")
    s.add_argument("--hours", type=int, default=None, help="posted within this many hours; default: from midnight of the latest posted date already read (never less than 24 h, at most 30 days)")
    s.add_argument("--input", default=str(INPUT_FILE), help="input CSV (default: job-radar-V3/input.csv)")
    s.add_argument("--workers", type=int, default=config.WORKERS, help="searches run in parallel")
    args = ap.parse_args()

    roles = load_input(Path(args.input))
    if args.role:
        wanted = {r.lower() for r in args.role}
        roles = [r for r in roles if r.role.lower() in wanted]
    if not roles:
        raise SystemExit("No matching roles in the input file")
    queries = queries_from(roles)
    hours, why = resolve_hours(args.hours, config.STATE_PATH, config.EXCEL_PATH, "Indeed")
    previous_latest = read_latest(config.STATE_PATH, config.EXCEL_PATH, "Indeed")
    started = time.time()
    print(f"{len(roles)} roles, {len(queries)} searches, window {why}, {args.workers} workers", flush=True)
    jobs, error, stats = engine.search(
        queries, hours, workers=args.workers,
        on_query=lambda q, n, kept: print(f"  [{q.role}] {q.keyword!r} in {q.location}: {n} found, {kept} kept", flush=True),
    )
    print(f"fetched {stats['fetched']}, dropped {stats['dropped_experience']} below the role's minimum experience, "
          f"kept {len(jobs)} unique jobs in {round((time.time() - started) / 60, 1)} min")
    if jobs:  # raw backup first, so a failure while writing Excel never loses a run
        backup = config.RUNS_DIR / f"indeed_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(chr(10).join(
            json.dumps(j, ensure_ascii=False, default=lambda o: o.isoformat() if isinstance(o, date) else str(o)) for j in jobs
        ), encoding="utf-8")
        print("saving to Excel ...", flush=True)
        path, n_new, n_upd, total = excel.save(jobs)
        print(f"{n_new} new, {n_upd} already known. {total} in {path.name}")
        if path.name == "Indeed.xlsx":
            record_run(config.STATE_PATH, jobs, error, previous_latest)
        if path.name != "Indeed.xlsx":
            print("!! Indeed.xlsx is open in Excel; wrote a timestamped copy instead. Close Excel and rerun.")
    else:
        print("No jobs read.")
    if error:
        print("!!", error)
        if "pushed back" in error:
            notify.popup("Job Radar: Indeed stopped", "Indeed pushed back.\nPartial results were saved. Rerun later.")


main()
