"""The progress page: a small local web server (127.0.0.1 only) that shows a run live and can start or stop one.

  python -m radar3 tracker        (starts the server and opens the page)    or double-click start_progress_v3.bat

Pages and calls:  GET /            the progress page (radar3/web/Progress.html)
                  GET /api/state   the live run, the last run, coverage, health, next scheduled run, Desktop launcher
                  GET /api/sources every source with its state, last good read and recent counts
                  POST /api/start  {"mode": "daily" | "all"}   start a run (refused while one is going)
                  POST /api/stop   stop the run that is going
Safety: listens on 127.0.0.1 only; the Host header must be 127.0.0.1 or localhost; a POST must carry the header X-Radar and, if it has an Origin,
that Origin must be this server (so another web page cannot start a run); nothing is ever written except through the run itself."""
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from urllib.parse import parse_qs, urlparse

from . import config, insight, notify, schedule
from .boards import BOARD_READER
from pipeline.runner import free_mb

from .runner import _pid_alive, health_report, load_stats
from .sources import coverage, load_sources

WEB_DIR = Path(__file__).resolve().parent / "web"
_cache: dict = {"next_run": ("", 0.0)}


def _lock_pid() -> int:
    try:
        return int((config.OUTPUT_DIR / "run.lock").read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def run_pid() -> int:
    """The process id of the run that is going, or 0."""
    pid = _lock_pid()
    return pid if pid and _pid_alive(pid) else 0


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def next_run_text() -> str:
    """The Task Scheduler line, cached for a minute (asking Windows takes about a second)."""
    text, at = _cache["next_run"]
    if time.time() - at > 60:
        try:
            text = schedule.show()
        except Exception as e:                                       # no PowerShell, or not allowed
            text = f"unknown ({type(e).__name__})"
        _cache["next_run"] = (text, time.time())
    return text


def _coverage_names(sources: list[dict]) -> dict:
    """coverage() with the page's words: working / waiting / parked / skipped / duplicate."""
    c = coverage(sources)
    return {"working": c["working"], "waiting": c["candidate"], "parked": c["parked"], "skipped": c["skipped"], "duplicate": c["duplicate"]}


def state_payload() -> dict:
    sources = load_sources()
    run = _read_json(config.STATE_PATH, {})
    running = bool(run_pid())
    if run.get("phase") in ("reading", "building") and not running:    # the process died without finishing
        run["phase"] = "stopped"
    by_id = {x["id"]: x for x in sources}
    progress = {sid: insight.board_progress(by_id[sid]["slug"]) for sid, row in (run.get("sources") or {}).items()
                if running and row.get("status") == "reading" and sid in by_id and by_id[sid]["reader"] == BOARD_READER}
    return {"now": datetime.now().isoformat(timespec="seconds"), "running": running, "pid": run_pid(), "run": run, "progress": progress, "free_mb": free_mb(),
            "last_run": _read_json(config.LAST_RUN_PATH, {}), "coverage": _coverage_names(sources),
            "health": [r for r in health_report(sources, load_stats()) if r["flag"]], "schedule": next_run_text(),
            "launcher_present": notify.launcher_present(), "launcher_name": notify.LAUNCHER_NAME, "port": config.PORT}


def sources_payload() -> list[dict]:
    stats, rows = load_stats(), []
    health = {r["id"]: r for r in health_report(load_sources(), stats)}
    for s in load_sources():
        st = stats.get(s["id"], {})
        state = ("duplicate" if s["cls"] == "X" else "skipped" if s["cls"] == "S" else "parked" if s["cls"] == "D" else "working" if s["enabled"] == "yes" else "waiting")
        rows.append({"id": s["id"], "name": s["name"], "list": s["sheet"], "reader": s["reader"], "schedule": s["schedule"] if state == "working" else "",
                     "state": state, "url": s["url"], "note": s["note"], "last_ok": st.get("last_ok"), "last_count": st.get("last_count"),
                     "counts": st.get("counts", []), "flag": (health.get(s["id"]) or {}).get("flag", ""), "matched": st.get("matched")})
    return rows


def runs_payload(limit: int = 20) -> list[dict]:
    """The last finished runs, newest first (radar3/output/runs.jsonl)."""
    try:
        lines = config.RUNS_PATH.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out[::-1]


def _desktop_files() -> list[dict]:
    desk = notify.desktop_dir()
    what = "One click does everything: starts this page, starts a full run (fast sources and job boards, about 40 minutes) and opens this page. The window closes by itself. The dashboard is the Dashboard link on this page."
    return [
        {"key": "desktop_run", "name": notify.LAUNCHER_NAME, "where": "Desktop", "path": desk / notify.LAUNCHER_NAME, "what": what},
        {"key": "project_run", "name": notify.PROJECT_LAUNCHER.name, "where": "Project folder", "path": notify.PROJECT_LAUNCHER, "what": "The same file; the Desktop copy just calls this one."},
    ]


def info_payload() -> dict:
    """Where the launcher files and output folders are, for the how-to-run panel."""
    root = str(config.ROOT)
    py = r".venv\Scripts\python"
    return {"project": root, "desktop": str(notify.desktop_dir()), "output": str(config.OUTPUT_DIR), "workbook": str(config.EXCEL_PATH), "dashboard": str(config.OUTPUT_DIR / "Dashboard.html"),
            "workbook_exists": config.EXCEL_PATH.exists(), "dashboard_exists": (config.OUTPUT_DIR / "Dashboard.html").exists(),
            "files": [{**f, "path": str(f["path"]), "exists": f["path"].exists()} for f in _desktop_files()],
            "commands": [
                {"label": "Run everything (fast sources and job boards)", "cmd": f'cd /d "{root}" && {py} -m radar3 run --mode all'},
                {"label": "Run the fast sources only (about 9 minutes, no Chrome)", "cmd": f'cd /d "{root}" && {py} -m radar3 run --mode all --skip-boards'},
                {"label": "Re-run one or more sources (ids from the Sources tab)", "cmd": f'cd /d "{root}" && {py} -m radar3 run --only J01 R33'},
                {"label": "See which sources need attention", "cmd": f'cd /d "{root}" && {py} -m radar3 health'},
                {"label": "Rebuild the dashboard from the last run", "cmd": f'cd /d "{root}" && {py} -m radar3 dashboard'},
            ]}


def problems_payload() -> dict:
    """Sources that did not run properly: category, reason, what to do, how often they failed lately. Plus the category mix and the reliability by day."""
    sources, stats = load_sources(), load_stats()
    health = health_report(sources, stats)
    history = insight.read_history()
    last = {sid: {"status": st.get("last_status", ""), "note": st.get("last_note", "")} for sid, st in stats.items()}
    rows = insight.problem_rows(sources, stats, last, health, history)
    cats: dict[str, int] = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    working = sum(1 for s_ in sources if s_.get("enabled") == "yes")
    return {"rows": rows, "categories": sorted(cats.items(), key=lambda x: -x[1]), "working": working, "healthy": working - len(rows), "by_day": insight.history_by_day(history),
            "parked": sum(1 for s_ in sources if s_["cls"] == "D"), "skipped": sum(1 for s_ in sources if s_["cls"] == "S")}


def log_payload(sid: str) -> dict:
    src = next((s_ for s_ in load_sources() if s_["id"] == sid), None)
    if not src:
        return {"ok": False, "error": "unknown source"}
    if src["reader"] != BOARD_READER:
        return {"ok": True, "text": "", "note": "This source reads a public API with plain requests and keeps no log file. Its last result and reason are shown above."}
    return {"ok": True, "text": insight.log_tail(src["slug"]), "note": "last lines of the job board's own log (latest run)"}


OPEN_FOLDERS = {"project": lambda: config.ROOT, "output": lambda: config.OUTPUT_DIR, "logs": lambda: config.OUTPUT_DIR / "logs", "desktop": notify.desktop_dir}
OPEN_FILES = {"workbook": lambda: config.EXCEL_PATH, "dashboard": lambda: config.OUTPUT_DIR / "Dashboard.html"}


def open_path(what: str) -> dict:
    """Open a folder or file on this PC from a fixed list. Launcher .bat files are only shown in Explorer, never run, so a click here cannot start a run."""
    try:
        if what in OPEN_FOLDERS:
            path = Path(OPEN_FOLDERS[what]())
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        elif what in OPEN_FILES:
            path = Path(OPEN_FILES[what]())
            if not path.exists():
                return {"ok": False, "error": f"{path.name} does not exist yet; run once first"}
            os.startfile(str(path))
        else:
            files = {f["key"]: f["path"] for f in _desktop_files()}
            if what not in files:
                return {"ok": False, "error": "not an allowed target"}
            if not files[what].exists():
                return {"ok": False, "error": "that file does not exist"}
            subprocess.Popen(["explorer", "/select,", str(files[what])])
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "error": str(e)[:100]}


def rerun(ids: list[str]) -> dict:
    """Read just these sources again (they must be working sources). Job boards among them open Chrome."""
    by_id = {s_["id"]: s_ for s_ in load_sources()}
    ok = [i for i in ids if i in by_id and by_id[i]["enabled"] == "yes"]
    if not ok:
        return {"ok": False, "error": "none of these are working sources"}
    res = start_run("all", boards=any(by_id[i]["reader"] == BOARD_READER for i in ok), only=ok)
    return {**res, "ids": ok, "ignored": [i for i in ids if i not in ok]}


def start_run(mode: str, boards: bool = True, only: list[str] | None = None) -> dict:
    """Start `python -m radar3 run` as a detached process. Refused while a run is going."""
    if mode not in ("daily", "all", "auto"):
        return {"ok": False, "error": "mode must be daily, all or auto"}
    if run_pid():
        return {"ok": False, "error": "a run is already going"}
    logs = config.OUTPUT_DIR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = open(logs / f"run_{datetime.now():%Y%m%d_%H%M%S}.log", "w", encoding="utf-8")
    p = subprocess.Popen([schedule.python_exe(), "-m", "radar3", "run", "--mode", mode, "--started-by", "progress page", "--no-popup", *([] if boards else ["--skip-boards"]), *(["--only", *only] if only else [])], cwd=str(config.ROOT),
                         stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW | 0x00000200, close_fds=True)
    return {"ok": True, "pid": p.pid, "mode": mode, "boards": boards, **({"only": only} if only else {})}


def stop_run() -> dict:
    """Stop the run that is going (the process and anything it started). What it already saved stays; sources not finished keep their previous jobs."""
    pid = run_pid()
    if not pid:
        return {"ok": False, "error": "no run is going"}
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    (config.OUTPUT_DIR / "run.lock").unlink(missing_ok=True)
    run = _read_json(config.STATE_PATH, {})
    if run:
        run["phase"] = "stopped"
        for s in run.get("sources", {}).values():
            if s.get("status") in ("waiting", "reading"):
                s["status"] = "stopped"
        run.setdefault("events", []).append({"t": datetime.now().isoformat(timespec="seconds"), "text": "run stopped from the progress page"})
        config.STATE_PATH.write_text(json.dumps(run, indent=1), encoding="utf-8")
    return {"ok": True, "stopped": pid}


class Handler(BaseHTTPRequestHandler):
    server_version = "RadarTracker"

    def log_message(self, *args):                                      # quiet
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"))

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "bad host"})
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (WEB_DIR / "Progress.html").read_bytes(), "text/html")
        if path == "/dashboard":
            dash = config.OUTPUT_DIR / "Dashboard.html"
            if dash.exists():
                return self._send(200, dash.read_bytes(), "text/html")
            return self._send(404, b"The dashboard has not been built yet. Run: python -m radar3 dashboard", "text/plain")
        if path == "/api/state":
            return self._json(200, state_payload())
        if path == "/api/sources":
            return self._json(200, sources_payload())
        if path == "/api/info":
            return self._json(200, info_payload())
        if path == "/api/problems":
            return self._json(200, problems_payload())
        if path == "/api/log":
            return self._json(200, log_payload((parse_qs(urlparse(self.path).query).get("id") or [""])[0]))
        if path == "/api/runs":
            return self._json(200, runs_payload())
        if path == "/api/ping":
            return self._json(200, {"radar": "v3"})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"error": "bad host"})
        origin = self.headers.get("Origin")
        if self.headers.get("X-Radar") != "1" or (origin and origin.split("://")[-1].split(":")[0] not in ("127.0.0.1", "localhost")):
            return self._json(403, {"error": "not from the progress page"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "bad json"})
        if self.path == "/api/start":
            return self._json(200, start_run(str(body.get("mode", "all")), bool(body.get("boards", True))))
        if self.path == "/api/rerun":
            ids = body.get("ids")
            return self._json(200, rerun([str(i) for i in ids]) if isinstance(ids, list) and ids else {"ok": False, "error": "no sources given"})
        if self.path == "/api/open":
            return self._json(200, open_path(str(body.get("what", ""))))
        if self.path == "/api/stop":
            return self._json(200, stop_run())
        self._json(404, {"error": "not found"})


def make_server(port: int = config.PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def already_serving(port: int = config.PORT) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
            return json.loads(r.read()).get("radar") == "v3"
    except Exception:
        return False


def ensure_server(port: int = config.PORT, wait_sec: float = 15) -> bool:
    """Make sure the progress page server is up, starting it detached (no window) when it is not."""
    if already_serving(port):
        return True
    exe = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(exe if exe.exists() else sys.executable), "-m", "radar3", "tracker", "--no-open"], cwd=str(config.ROOT),
                     creationflags=subprocess.CREATE_NO_WINDOW | 0x00000200, close_fds=True)
    end = time.time() + wait_sec
    while time.time() < end:
        if already_serving(port):
            return True
        time.sleep(0.4)
    return False


def launch(run: bool = True, port: int = config.PORT) -> int:
    """The one-click entry: server up, run started (unless one is already going), progress page open. Nothing stays in a window."""
    if not ensure_server(port):
        print("could not start the progress page; port", port, "may be in use")
        return 1
    if run:
        res = start_run("all")
        print("run started" if res.get("ok") else f"not started: {res.get('error')}")
    webbrowser.open(f"http://127.0.0.1:{port}/")
    return 0


def serve(open_browser: bool = True, port: int = config.PORT) -> int:
    url = f"http://127.0.0.1:{port}/"
    if already_serving(port):
        print("the progress page is already running:", url)
        if open_browser:
            webbrowser.open(url)
        return 0
    try:
        server = make_server(port)
    except OSError as e:
        print(f"port {port} is in use by something else ({e}); close it and try again")
        return 1
    print("progress page:", url, " (close this window to stop it; a run keeps going without it)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(serve())
