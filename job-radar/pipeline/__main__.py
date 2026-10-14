"""Command line:
  python -m pipeline run [--only SITE ...] [--skip SITE ...] [--no-popup]   run the site workflows in lanes, then build Job_Radar.xlsx
  python -m pipeline build                                                    only rebuild Job_Radar.xlsx from the site workbooks
  python -m pipeline schedule [--time HH:MM] | --show | --remove              the daily Windows task (default 09:00)
  python -m pipeline tracker                                                  the live tracker page (Start button, live status)
"""
import argparse
import json
import time
from datetime import datetime

from . import build as build_mod
from . import history, monitor
from . import state as state_mod
from . import config, notify, runner, schedule
from .report import RunReport
from .load import read_all


def _keep_awake(on: bool) -> None:
    """While a run is going the PC must not go to sleep (Windows only)."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))   # ES_CONTINUOUS [| ES_SYSTEM_REQUIRED]
    except Exception:
        pass


def _summary_text(results: list[dict], stats: dict) -> str:
    lines = [f"{stats['new_today']} new jobs today ({stats['new_today_bengaluru']} in Bengaluru). {stats['matched']} matched jobs in all, "
             f"{stats['duplicates_removed']} duplicates removed."]
    for r in results:
        if r["status"] != "ok":
            lines.append(f"- {r['site']}: {r['status']}" + (f" ({r['problems'][0][:90]})" if r["problems"] else ""))
    if all(r["status"] == "ok" for r in results):
        lines.append("All sites finished without problems.")
    lines.append(f"File: {stats['written']}")
    return "\n".join(lines)


def cmd_build() -> dict:
    sites = config.SITES
    site_jobs = read_all(sites)
    path, stats = build_mod.build(site_jobs)
    print(f"read {stats['total_read']} jobs {stats['read']}")
    print(f"{stats['unique']} unique after removing {stats['duplicates_removed']} duplicates ({stats['on_several_sites']} jobs are on several sites)")
    print(f"{stats['matched']} match a role title ({stats['bengaluru']} in Bengaluru), {stats['unmatched']} fit no role (tab 'Unmatched')")
    print("by role:", {r: n for r, n in stats["by_role"].items() if n})
    if stats.get("parked_non_tech"):
        print(f"{stats['parked_non_tech']} jobs from the parked non-tech roles left out")
    print(f"new today: {stats['new_today']} ({stats['new_today_bengaluru']} in Bengaluru)")
    print(f"wrote {path}")
    if path.name != config.EXCEL_PATH.name:
        print("!! Job_Radar.xlsx is open in Excel; wrote a timestamped copy instead. Close Excel and run `python -m pipeline build`.")
    return stats


def cmd_run(only: list[str] | None, skip: list[str] | None, popup: bool, series: bool = False) -> None:
    sites = [s for s in config.SITES if (not only or s.name in only) and s.name not in (skip or [])]
    if not sites:
        raise SystemExit("No sites selected")
    if state_mod.is_running(state_mod.read()):
        raise SystemExit("A run is already going (see pipeline/output/run_state.json). Wait for it, or stop it from the tracker.")
    started = time.time()
    for stale in (config.CONTROL_DIR.glob("*.json") if config.CONTROL_DIR.exists() else []):
        stale.unlink(missing_ok=True)                                  # commands left over from an earlier run
    print(config.activate_scope(), flush=True)
    lanes = config.lanes_for(sites, series)
    run_dir = config.LOGS_DIR / datetime.now().strftime("%Y-%m-%d_%H%M")
    report = RunReport(run_dir)
    live = state_mod.RunState()
    live.begin([[s.name for s in lane] for lane in lanes], config.ROLE_SCOPE, run_dir, series)
    print(f"{datetime.now():%Y-%m-%d %H:%M} starting {len(sites)} sites in {len(lanes)} lanes: "
          + " | ".join(" > ".join(s.name for s in lane) for lane in lanes), flush=True)
    _keep_awake(True)
    sampler = monitor.Sampler(live.resources).start()
    try:
        def on_done(r: dict) -> None:
            print(f"  {r['site']}: {r['status']} in {r['minutes']} min" + (" (second try)" if r.get("retried") else "")
                  + (f", {r['new']} new / {r['total']} in workbook" if r["new"] is not None else ""), flush=True)
            live.site_event(r)
            text = report.event(r)
            if text:
                print("\n" + text, flush=True)

        results = runner.run_sites(sites, lanes=lanes, on_done=on_done, logs_dir=run_dir, on_start=live.site_started,
                                   control=runner.read_control, on_note=live.note)
    except BaseException as exc:
        live.fail(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        sampler.finish()
        _keep_awake(False)
    print(f"all sites done in {round((time.time() - started) / 60, 1)} min; building Job_Radar.xlsx", flush=True)
    live.phase("building", "all sites done; building Job_Radar.xlsx")
    try:
        stats = cmd_build()
    except BaseException as exc:
        live.fail(f"build failed: {type(exc).__name__}: {exc}")
        raise
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.SUMMARY_PATH.write_text(json.dumps({"finished": datetime.now().isoformat(timespec="seconds"), "sites": results, "stats": stats},
                                              indent=2, default=str), encoding="utf-8")
    text = _summary_text(results, stats)
    print(text)
    live.finish(stats, text)
    history.record_from_state(live.data)
    if popup and config.POPUP_AT_END:
        notify.popup("Job Radar: daily run finished", text)


def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline", description="Job Radar V2: run every site workflow, then build the combined workbook")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the site workflows in lanes, then build Job_Radar.xlsx")
    r.add_argument("--only", nargs="+", choices=[s.name for s in config.SITES], help="run only these sites")
    r.add_argument("--skip", nargs="+", choices=[s.name for s in config.SITES], help="run all sites except these")
    r.add_argument("--no-popup", action="store_true", help="do not show the message box at the end")
    r.add_argument("--roles", choices=["tech", "all"], default=None, help=f"which roles to read (default {config.ROLE_SCOPE})")
    r.add_argument("--series", action="store_true", help="run the sites one after another (shortest first) and print a report after each")
    b = sub.add_parser("build", help="rebuild Job_Radar.xlsx from the site workbooks without running any site")
    b.add_argument("--roles", choices=["tech", "all"], default=None, help=f"which roles to include (default {config.ROLE_SCOPE})")
    hh = sub.add_parser("history", help="the run history used by the Performance tab")
    hh.add_argument("--backfill", action="store_true", help="add the runs found in output/logs that are not in the history yet")
    t = sub.add_parser("tracker", help="open the live tracker page (a local web page with a Start button)")
    t.add_argument("--port", type=int, default=8770)
    t.add_argument("--no-browser", action="store_true", help="do not open the browser")
    s = sub.add_parser("schedule", help="register the daily Windows task")
    s.add_argument("--time", default=config.RUN_TIME, help=f"time of day, HH:MM (default {config.RUN_TIME})")
    s.add_argument("--show", action="store_true", help="show the registered task")
    s.add_argument("--remove", action="store_true", help="remove the task")
    args = ap.parse_args()

    if getattr(args, "roles", None):
        config.ROLE_SCOPE = args.roles
    if args.cmd == "history":
        print(f"{history.backfill()} runs added from the logs" if args.backfill else f"{len(history.known_runs())} runs in the history")
    elif args.cmd == "tracker":
        from . import tracker
        tracker.serve(args.port, not args.no_browser)
    elif args.cmd == "build":
        cmd_build()
    elif args.cmd == "run":
        cmd_run(args.only, args.skip, not args.no_popup, args.series)
    else:
        if args.show:
            print(schedule.show())
        elif args.remove:
            print(schedule.remove()[1])
        else:
            ok, message = schedule.register(args.time)
            print(message)
            if ok:
                print(schedule.show())


main()
