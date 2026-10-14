"""Command line:  python -m cutshort search [--hours N] [--input FILE]   |   python -m cutshort check

Reads the public Cutshort job lists in cutshort/lists.csv (data science for India, Bengaluru and remote). input.csv only sets
the experience rule: the lowest minimum experience of the tech roles in it (Experience above 0)."""
import argparse
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from common.inputs import INPUT_FILE, load_input
from common.window import read_latest, record_run, resolve_hours

from . import config, excel, notify, session
from . import search as search_mod


def main() -> None:
    ap = argparse.ArgumentParser(prog="cutshort", description="Cutshort workflow (real Chrome, public data science job lists, no login)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="open Chrome so you can pass a Cutshort human check by hand if one ever appears (do not sign in)")
    s = sub.add_parser("search", help="read the newest jobs into cutshort/output/Cutshort.xlsx")
    s.add_argument("--hours", type=int, default=None, help="posted within this many hours; default: from midnight of the latest posted date already read (at least 24 h, at most 7 days)")
    s.add_argument("--input", default=str(INPUT_FILE), help="input CSV (default: job-radar-V3/input.csv)")
    args = ap.parse_args()

    if args.cmd == "check":
        print("Done." if session.wait_for_human() else "No jobs seen. Run it again.")
        return

    tech = [r.min_experience for r in load_input(Path(args.input)) if r.min_experience >= 1]
    if not tech:
        raise SystemExit("No tech roles in input.csv (Cutshort's lists are tech jobs: minimum experience above 0)")
    min_experience = min(tech)
    hours, why = resolve_hours(args.hours, config.STATE_PATH, config.EXCEL_PATH, excel.SHEET, maximum=config.MAX_WINDOW_HOURS)
    previous_latest = read_latest(config.STATE_PATH, config.EXCEL_PATH, excel.SHEET)
    lists = config.load_lists()
    started = time.time()
    print(f"{len(lists)} Cutshort lists, window {why}, experience: top of range at least {min_experience}", flush=True)
    jobs, error, stats = search_mod.search(
        hours, min_experience, lists,
        on_list=lambda l, n, total, kept: print(f"  {l.label}: {n} newest of {total} jobs read, {kept} kept", flush=True),
    )
    print(f"read {stats['read']} jobs on {stats['pages']} pages in {round(time.time() - started)} s; kept {len(jobs)} unique jobs "
          f"({stats['outside_window']} outside the window, {stats['dropped_internship']} internships, {stats['dropped_experience']} dropped by the experience rule)")
    for r in stats["reports"]:
        if hours and r["read"] >= 50 and r["oldest"] and datetime.combine(r["oldest"], datetime.min.time()) > datetime.now() - timedelta(hours=hours):
            print(f"  !! {r['label']}: all {r['read']} newest jobs are inside the window, so older jobs may be missing from this list")
    if jobs:  # raw backup first, so a failure while writing Excel never loses a run
        backup = config.RUNS_DIR / f"cutshort_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(chr(10).join(
            json.dumps(j, ensure_ascii=False, default=lambda o: o.isoformat() if isinstance(o, date) else str(o)) for j in jobs
        ), encoding="utf-8")
        print("saving to Excel ...", flush=True)
        path, n_new, n_upd, total = excel.save(jobs)
        print(f"{n_new} new, {n_upd} already known. {total} in {path.name}")
        if path.name == "Cutshort.xlsx":
            record_run(config.STATE_PATH, jobs, error, previous_latest)
        else:
            print("!! Cutshort.xlsx is open in Excel; wrote a timestamped copy instead. Close Excel and rerun.")
    else:
        print("No jobs inside the window.")
    if error:
        print("!!", error)
        if "human check" in error:
            notify.popup("Job Radar: Cutshort needs you", "Cutshort is asking for the human check.\nDouble-click check_cutshort.bat, pass it (do not sign in), then rerun.")


main()
