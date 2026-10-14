"""Command line.  Run from the project folder:
  python -m radar3 run [--mode auto|daily|all] [--only R33 R44 ...] [--no-popup] [--skip-boards]
  python -m radar3 build            (rebuild the workbook from the last good reads, no network)
  python -m radar3 sources          (coverage and what is due)
  python -m radar3 health           (which sources are healthy, stale, empty or broken)
  python -m radar3 schedule [--time 08:30] [--show] [--remove]     (the morning task in Windows Task Scheduler)
  python -m radar3 install-launcher (put 'Job Radar V3.bat' on the Desktop)
  python -m radar3 dashboard        (rebuild Dashboard.html from the last snapshot)
  python -m radar3 tracker [--no-open]  (the progress page on http://127.0.0.1:8771)"""
import argparse
import json
import sys
from datetime import date

from . import config, dashboard, notify, schedule, tracker
from .build import build
from .runner import AlreadyRunning, health_report, load_source_jobs, load_stats, run
from .sources import coverage, enabled, load_sources, select


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="radar3")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--mode", choices=["auto", "daily", "all"], default="auto")
    r.add_argument("--only", nargs="+", metavar="ID")
    r.add_argument("--started-by", default="command line")
    r.add_argument("--no-popup", action="store_true")
    r.add_argument("--skip-boards", action="store_true", help="leave out the job boards (LinkedIn, Naukri...): they take about 35 minutes")
    sub.add_parser("build")
    sub.add_parser("sources")
    sub.add_parser("health")
    s = sub.add_parser("schedule")
    s.add_argument("--time", default=config.RUN_TIME)
    s.add_argument("--show", action="store_true")
    s.add_argument("--remove", action="store_true")
    s.add_argument("--with-boards", action="store_true", help="the scheduled run also reads the job boards (disable V2's own 09:00 task first)")
    sub.add_parser("import-v2", help="one time: carry V2's Status, Notes and First seen into V3 (V2 is only read)")
    sub.add_parser("install-launcher")
    sub.add_parser("dashboard")
    t = sub.add_parser("tracker")
    t.add_argument("--no-open", action="store_true")
    t.add_argument("--launch", action="store_true", help="one click: start the page server (no window), start a full run, open the page")
    t.add_argument("--no-run", action="store_true", help="with --launch: open the page without starting a run")
    args = p.parse_args(argv)

    if args.cmd == "schedule":
        print(schedule.show() if args.show else schedule.remove() if args.remove else schedule.register(args.time, args.with_boards))
        return 0
    if args.cmd == "dashboard":
        print("wrote", dashboard.build_dashboard())
        return 0
    if args.cmd == "tracker":
        if args.launch:
            return tracker.launch(run=not args.no_run)
        return tracker.serve(open_browser=not args.no_open)
    if args.cmd == "import-v2":
        from .build import import_v2
        print(f"saved {import_v2()} V2 links to {config.V2_SEED_PATH}; the next build merges them (V3's own Status and Notes win)")
        return 0
    if args.cmd == "install-launcher":
        print("wrote", notify.install_launcher())
        return 0
    sources = load_sources()
    if args.cmd == "sources":
        due = select(sources, "auto", load_stats(), date.today())
        print("coverage:", json.dumps(coverage(sources)))
        print(f"enabled {len(enabled(sources))}, due now {len(due)}: " + ", ".join(s["id"] for s in due))
        return 0
    if args.cmd == "health":
        rows = health_report(sources, load_stats())
        bad = [r for r in rows if r["flag"]]
        print(f"{len(rows) - len(bad)} of {len(rows)} enabled sources healthy")
        for r in bad:
            print(f"  {r['id']} {r['name'][:28]:28} {r['flag']:10} last good read: {r['last_ok'] or 'never'}  counts {r['counts']}")
        if bad:
            print("What to do: a source that returned nothing twice, or is stale, has probably changed. Re-read its page with the browser tools "
                  "(see CLAUDE.md, 'Which browser tool for discovery') and fix its reader or slug.")
        return 1 if bad else 0
    if args.cmd == "build":
        jobs = {s["name"] + f" ({s['id']})": load_source_jobs(s["id"]) for s in enabled(sources)}
        path, stats = build({k: v for k, v in jobs.items() if v})
        print("wrote", path, json.dumps({k: v for k, v in stats.items() if k not in ("read", "by_role")}))
        return 0
    if args.started_by == "scheduler":
        tracker.ensure_server()                                        # the one progress page must be up to show a scheduled run (no browser is opened)
    try:
        summary = run(args.mode, args.only, started_by=args.started_by, boards=not args.skip_boards)
    except AlreadyRunning as e:
        print(e)
        return 2
    b = summary["build"]
    print(f"done in {summary['seconds']}s: {summary['ok']}/{summary['sources_run']} sources ok; {b['matched']} matched jobs "
          f"({b['remote_open_to_india']} remote open to India, {b['remote_check_eligibility']} remote to check, {b['bengaluru']} Bengaluru, "
          f"{b['hyderabad_chennai']} Hyderabad/Chennai, {b['rest_of_india']} rest of India); {b['new_today']} new today")
    for sid, pr in summary["problems"].items():
        print(f"  problem: {sid} {pr['status']} {pr['note']}")
    print("workbook:", summary["workbook"])
    if not args.no_popup:
        notify.popup(notify.message(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
