"""Command line:  python -m wellfound search [--role NAME ...] [--hours N]   |   python -m wellfound check

Reads job-radar-V3/input.csv (Role, Keywords, Experience, Location). Tech roles only (minimum experience above 0)."""
import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path

from common.inputs import INPUT_FILE, load_input, queries_from
from common.window import read_latest, record_run, resolve_hours

from . import config, excel, notify, session
from . import search as search_mod


def main() -> None:
    ap = argparse.ArgumentParser(prog="wellfound", description="Wellfound workflow (real Chrome, public pages, no login, polite paging)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="open Chrome so you can pass Wellfound's human check by hand if it ever appears (do not sign in)")
    s = sub.add_parser("search", help="read the newest tech jobs for the roles in input.csv into wellfound/output/Wellfound.xlsx")
    s.add_argument("--role", action="append", help="only this role from input.csv (repeatable); default all tech roles")
    s.add_argument("--hours", type=int, default=None, help="posted within this many hours; default: from midnight of the latest posted date already read (at least 24 h, at most 7 days); 0 = no time filter")
    s.add_argument("--input", default=str(INPUT_FILE), help="input CSV (default: job-radar-V3/input.csv)")
    s.add_argument("--workers", type=int, default=None, help="Chromes sharing the page queue (default and maximum 8)")
    s.add_argument("--keep-all-locations", action="store_true", help="also keep remote jobs that name a place outside India (default: India, remote-India and remote-anywhere only)")
    s.add_argument("--include-non-tech", action="store_true", help="also search roles with minimum experience 0 (Wellfound has no pages for most of them)")
    args = ap.parse_args()

    if args.cmd == "check":
        print("Done." if session.wait_for_human() else "No jobs seen. Run it again.")
        return

    roles = load_input(Path(args.input))
    if not args.include_non_tech:
        roles = [r for r in roles if r.min_experience >= config.TECH_ONLY_MIN_EXPERIENCE]
    if args.role:
        wanted = {r.lower() for r in args.role}
        roles = [r for r in roles if r.role.lower() in wanted]
    if not roles:
        raise SystemExit("No matching roles (Wellfound searches tech roles only: minimum experience above 0 in input.csv)")
    queries = queries_from(roles)
    hours, why = resolve_hours(args.hours, config.STATE_PATH, config.EXCEL_PATH, excel.SHEET, maximum=config.MAX_WINDOW_HOURS)
    previous_latest = read_latest(config.STATE_PATH, config.EXCEL_PATH, excel.SHEET)
    started = time.time()
    targets, _ = search_mod.plan(queries)
    print(f"{len(roles)} roles, {len(queries)} keywords, {len(targets)} Wellfound page lists to read, window {why}", flush=True)
    jobs, error, stats = search_mod.search(
        queries, hours, workers=args.workers, keep_all_locations=args.keep_all_locations,
        on_page=lambda t, n, new: print(f"  [{t.role}] {t.slug} ({t.kind}) page {n}: {new} new jobs", flush=True),
    )
    for note in stats["notes"]:
        print("  note:", note)
    print(f"{stats['chromes']} Chromes read {stats['read']} jobs on {stats['pages']} pages in {round((time.time() - started) / 60, 1)} min")
    print(f"kept {stats['in_window']} unique jobs; dropped: {stats['outside_window']} outside the window, "
          f"{stats['dropped_location']} outside India or not remote-anywhere, {stats['dropped_experience']} by the experience rule")
    print("  pages read per Chrome:", stats["pages_per_chrome"])
    for role, r in stats["per_role"].items():
        print(f"  {role:28} pages {r['pages']:3}  read {r['read']:4}  kept {r['kept']:4}")
    if jobs:  # raw backup first, so a failure while writing Excel never loses a run
        backup = config.RUNS_DIR / f"wellfound_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(chr(10).join(
            json.dumps(j, ensure_ascii=False, default=lambda o: o.isoformat() if isinstance(o, date) else str(o)) for j in jobs
        ), encoding="utf-8")
        print("saving to Excel ...", flush=True)
        path, n_new, n_upd, total = excel.save(jobs)
        print(f"{n_new} new, {n_upd} already known. {total} in {path.name}")
        if path.name == "Wellfound.xlsx":
            record_run(config.STATE_PATH, jobs, error, previous_latest)
        else:
            print("!! Wellfound.xlsx is open in Excel; wrote a timestamped copy instead. Close Excel and rerun.")
    else:
        print("No jobs inside the window.")
    if error:
        print("!!", error)
        if "human check" in error:
            notify.popup("Job Radar: Wellfound needs you", "Wellfound is asking for the human check.\nDouble-click check_wellfound.bat, pass it (do not sign in), then rerun.")


main()
