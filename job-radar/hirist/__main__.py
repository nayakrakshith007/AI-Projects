"""Command line:  python -m hirist search [--role NAME ...] [--hours N] [--method both|search|tag]   |   python -m hirist check

Reads job-radar-V3/input.csv (Role, Keywords, Experience, Location). Runs both Hirist methods by default and compares them."""
import argparse
import csv
import json
import time
from datetime import date, datetime
from pathlib import Path

from common.inputs import INPUT_FILE, load_input, queries_from
from common.window import read_latest, record_run, resolve_hours

from . import config, excel, notify, session
from . import search as search_mod


def main() -> None:
    ap = argparse.ArgumentParser(prog="hirist", description="Hirist workflow (real Chrome, Hirist's own date filter, tag pages and search)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="open Chrome so you can pass a Hirist human check by hand if one ever appears (do not sign in)")
    s = sub.add_parser("search", help="read the newest jobs for the roles in input.csv into hirist/output/Hirist.xlsx")
    s.add_argument("--role", action="append", help="only this role from input.csv (repeatable); default all roles")
    s.add_argument("--hours", type=int, default=None, help="posted within this many hours; default: from midnight of the latest posted date already read (at least 24 h, at most 7 days)")
    s.add_argument("--input", default=str(INPUT_FILE), help="input CSV (default: job-radar-V3/input.csv)")
    s.add_argument("--method", choices=["both", "search", "tag"], default="both", help="which Hirist method to run (default both, compared at the end)")
    s.add_argument("--workers", type=int, default=None, help=f"Chromes sharing the page queue (default {config.WORKERS}, at most {config.WORKERS_MAX})")
    s.add_argument("--include-non-tech", action="store_true", help="also search roles with minimum experience 0 (Hirist is a tech job site)")
    args = ap.parse_args()

    if args.cmd == "check":
        print("Done." if session.wait_for_human() else "No jobs seen. Run it again.")
        return

    roles = load_input(Path(args.input))
    if not args.include_non_tech:
        roles = [r for r in roles if r.min_experience >= 1]
    if args.role:
        wanted = {r.lower() for r in args.role}
        roles = [r for r in roles if r.role.lower() in wanted]
    if not roles:
        raise SystemExit("No matching roles (Hirist searches tech roles only: minimum experience above 0 in input.csv)")
    queries = queries_from(roles)
    hours, why = resolve_hours(args.hours, config.STATE_PATH, config.EXCEL_PATH, excel.SHEET, maximum=config.MAX_WINDOW_HOURS)
    previous_latest = read_latest(config.STATE_PATH, config.EXCEL_PATH, excel.SHEET)
    methods = config.METHODS if args.method == "both" else (args.method,)
    started = time.time()
    targets, _ = search_mod.plan(queries, methods=methods)
    print(f"{len(roles)} roles, {len(queries)} keywords, {len(targets)} Hirist lists ({'+'.join(methods)}), window {why}, "
          f"Hirist filter posting={config.posting_days(hours)} days", flush=True)
    jobs, error, stats = search_mod.search(
        queries, hours, workers=args.workers, methods=methods,
        on_page=lambda t, n, new: print(f"  [{t.role}] {t.method}:{t.slug} page {n}: {new} new jobs", flush=True),
    )
    for note in stats["notes"]:
        print("  note:", note)
    print(f"{stats['chromes']} Chromes read {stats['read']} jobs on {stats['pages']} pages in {round((time.time() - started) / 60, 1)} min; "
          f"kept {len(jobs)} unique jobs ({stats['outside_window']} outside the window, {stats['dropped_experience']} dropped by the experience rule)")
    print("  pages read per Chrome:", stats["pages_per_chrome"])
    if len(methods) == 2:
        print(f"  {'role':26} {'search':>7} {'(title)':>8} {'tag':>5} {'(title)':>8} {'both':>5} {'only s':>7} {'only t':>7} {'union':>6} {'(title)':>8}")
        for r in stats["compare"]:
            print(f"  {r['role']:26} {r['search']:7} {r['search_match_title']:8} {r['tag']:5} {r['tag_match_title']:8} {r['both']:5} "
                  f"{r['only_search']:7} {r['only_tag']:7} {r['union']:6} {r['union_match_title']:8}")
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.COMPARE_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(stats["compare"][0].keys()))
            w.writeheader()
            w.writerows(stats["compare"])
    if jobs:  # raw backup first, so a failure while writing Excel never loses a run
        backup = config.RUNS_DIR / f"hirist_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(chr(10).join(
            json.dumps(j, ensure_ascii=False, default=lambda o: o.isoformat() if isinstance(o, date) else str(o)) for j in jobs
        ), encoding="utf-8")
        print("saving to Excel ...", flush=True)
        path, n_new, n_upd, total = excel.save(jobs)
        print(f"{n_new} new, {n_upd} already known. {total} in {path.name}")
        if path.name == "Hirist.xlsx":
            record_run(config.STATE_PATH, jobs, error, previous_latest)
        else:
            print("!! Hirist.xlsx is open in Excel; wrote a timestamped copy instead. Close Excel and rerun.")
    else:
        print("No jobs inside the window.")
    if error:
        print("!!", error)
        if "human check" in error:
            notify.popup("Job Radar: Hirist needs you", "Hirist is asking for the human check.\nDouble-click check_hirist.bat, pass it (do not sign in), then rerun.")


main()
