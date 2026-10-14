"""The live tracker: a small local web server (nothing leaves this PC) for Tracker.html.

    python -m pipeline tracker            ->  http://127.0.0.1:8770

The page shows which site is reading right now, how far each one is, what each added, and the problems of the run. The Start button runs
`python -m pipeline run` in the background (it keeps going if you close the page or this window); Stop ends it. The server only reads the
run's own files (run_state.json, the site logs, errors.log, last_run.json), so a run started by the 09:00 task or the command line
shows up in the page as well."""
import json
import re
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config, history, runner, state

PORT = 8770
HTML = Path(__file__).with_name("Pipeline_Workflow.html")          # the main page: the dark pipeline diagram with the live tabs
CLASSIC = Path(__file__).with_name("Tracker.html")                 # the first, plain tracker page, kept at /classic
TOTAL = re.compile(r"(\d+) (?:searches|[A-Za-z]+ lists)")
ITEM = re.compile(r"^\s*\[(?P<role>[^\]]+)\] (?P<rest>.+)$")
SPLIT = re.compile(r" page \d+| offset \d+|: ")


def log_progress(text: str) -> dict:
    """What a site log says about its progress: searches started out of the planned total, the last activity line, the planned total."""
    lines = [l for l in text.splitlines() if l.strip()]
    total = None
    for l in lines[:6]:
        m = TOTAL.search(l)
        if m:
            total = int(m.group(1))
            break
    seen, last = set(), ""
    for l in lines:
        m = ITEM.match(l)
        if m:
            seen.add((m["role"], SPLIT.split(m["rest"])[0].strip(" ,")))
            last = l.strip()
        elif not l.startswith(("Call log", "  -", "  note")) and not last:
            last = l.strip()
    if not last and lines:
        last = lines[-1].strip()
    return {"searches_started": len(seen), "searches_total": total, "last_line": last[:200], "lines": len(lines)}


def _tail(path: Path, max_bytes: int = 400_000) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _parse_time(value: str | None) -> float | None:
    try:
        return datetime.fromisoformat(value).timestamp() if value else None
    except ValueError:
        return None


def build_status() -> dict:
    data = state.read()
    now = time.time()
    out: dict = {"server_time": datetime.now().isoformat(timespec="seconds"), "phase": "idle", "run": None, "last_run": None,
                 "workbook": None, "errors": []}
    try:
        last = json.loads(config.SUMMARY_PATH.read_text(encoding="utf-8"))
        out["last_run"] = {"finished": last.get("finished"), "sites": [{k: s.get(k) for k in ("site", "status", "minutes", "new", "total")}
                                                                      for s in last.get("sites", [])], "stats": last.get("stats")}
    except (OSError, ValueError):
        pass
    if config.EXCEL_PATH.exists():
        st = config.EXCEL_PATH.stat()
        out["workbook"] = {"name": config.EXCEL_PATH.name, "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                           "size_kb": round(st.st_size / 1024)}
    if not data:
        return out
    phase = data.get("phase", "idle")
    if phase in ("running", "building") and not state.pid_alive(data.get("pid")):
        phase = "interrupted"                                        # the process is gone without having finished
    out["phase"] = phase
    sites = {}
    for name, s in data.get("sites", {}).items():
        s = dict(s)
        log = Path(s["log"]) if s.get("log") else None
        if log and log.exists():
            prog = log_progress(_tail(log))
            s.update(prog)
            s["quiet_seconds"] = round(now - log.stat().st_mtime)
        if s.get("status") in ("running", "restarting") and phase == "interrupted":
            s["status"] = "stopped"
        sites[name] = s
    run = {k: data.get(k) for k in ("pid", "started", "finished", "scope", "series", "lanes", "stats", "summary", "error", "control")}
    run["resources"] = data.get("resources")
    run["sites"] = sites
    run["events"] = (data.get("events") or [])[-40:]
    run["elapsed_seconds"] = round(((_parse_time(data.get("finished")) or now) - (_parse_time(data.get("started")) or now)))
    out["run"] = run
    if data.get("run_dir"):
        out["errors"] = [l for l in _tail(Path(data["run_dir"]) / "errors.log", 60_000).splitlines() if l.strip()][-25:]
    return out


def read_log(site: str, lines: int = 80) -> str:
    data = state.read() or {}
    s = data.get("sites", {}).get(site)
    if not s or not s.get("log"):
        return ""
    log = Path(s["log"]).resolve()
    if config.LOGS_DIR.resolve() not in log.parents:               # only logs of the pipeline itself
        return ""
    return "\n".join(_tail(log, 60_000).splitlines()[-lines:])


def start_run(body: dict) -> tuple[int, dict]:
    if state.is_running(state.read()):
        return 409, {"error": "A run is already going."}
    cmd = [sys.executable, "-m", "pipeline", "run", "--no-popup"]
    roles = body.get("roles")
    if roles in ("tech", "all"):
        cmd += ["--roles", roles]
    if body.get("series"):
        cmd.append("--series")
    only = [s for s in body.get("only") or [] if s in config.SITE_BY_NAME]
    if only:
        cmd += ["--only", *only]
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = open(config.OUTPUT_DIR / "tracker_start.out", "w", encoding="utf-8")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(cmd, cwd=config.ROOT, stdout=out, stderr=subprocess.STDOUT, creationflags=flags,
                     env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    return 200, {"started": True, "command": " ".join(cmd[1:])}


def site_action(site: str, action: str) -> tuple[int, dict]:
    """Ask the running pipeline to stop or restart one site: the command goes into a file the pipeline reads within a couple of seconds."""
    data = state.read()
    if not state.is_running(data) or data.get("phase") != "running":
        return 409, {"error": "No run is going (or it is already building the workbook)."}
    if not data.get("control"):
        return 409, {"error": "This run was started by an older version that cannot take stop or restart commands. Use the big Stop button, or wait for it to end."}
    if site not in (data.get("sites") or {}):
        return 404, {"error": f"{site} is not part of this run."}
    if action not in ("stop", "restart"):
        return 400, {"error": "action must be stop or restart"}
    config.CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    (config.CONTROL_DIR / f"{time.time_ns()}_{site}_{action}.json").write_text(json.dumps({"site": site, "action": action}), encoding="utf-8")
    return 200, {"queued": True, "site": site, "action": action}


def stop_run() -> tuple[int, dict]:
    data = state.read()
    if not state.is_running(data):
        return 409, {"error": "No run is going."}
    started = _parse_time(data.get("started")) or time.time()
    rs = state.RunState()
    rs.data = data
    rs.phase("stopping", "stop requested from the tracker")           # shown at once, while the processes are being ended
    subprocess.run(["taskkill", "/PID", str(data["pid"]), "/T", "/F"], capture_output=True, timeout=30)
    time.sleep(1)
    runner.stop_leftover_chromes(started)
    for s in data.get("sites", {}).values():
        if s.get("status") in ("running", "restarting"):
            s["status"] = "stopped"
    rs.phase("stopped", "run stopped from the tracker")
    history.record_from_state(rs.data)
    return 200, {"stopped": True}


class Handler(BaseHTTPRequestHandler):
    server_version = "JobRadarTracker"

    def log_message(self, *args) -> None:                          # quiet
        pass

    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._json(403, {"error": "bad host"})
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/classic":
            self._send(200, CLASSIC.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/status":
            self._json(200, build_status())
        elif url.path == "/api/history":
            q = parse_qs(url.query)
            scope = (q.get("scope") or ["any"])[0]
            mode = (q.get("mode") or ["any"])[0]
            summ = history.summary(history.read_records(), scope if scope in ("tech", "all", "any") else "any", (q.get("only_ok") or ["0"])[0] == "1",
                                   mode if mode in ("series", "lanes", "parallel") else "any")
            summ["experiments"] = history.experiments()
            self._json(200, summ)
        elif url.path == "/api/log":
            q = parse_qs(url.query)
            self._send(200, read_log((q.get("site") or [""])[0]).encode("utf-8"), "text/plain; charset=utf-8")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._host_ok() or self.headers.get("X-Tracker") != "1":     # a custom header keeps other web pages from posting here
            return self._json(403, {"error": "forbidden"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/api/start":
            self._json(*start_run(body))
        elif self.path == "/api/stop":
            self._json(*stop_run())
        elif self.path in ("/api/site/stop", "/api/site/restart"):
            self._json(*site_action(str(body.get("site") or ""), self.path.rsplit("/", 1)[1]))
        else:
            self._json(404, {"error": "not found"})


def serve(port: int = PORT, open_browser: bool = True) -> None:
    url = f"http://127.0.0.1:{port}"
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        print(f"The tracker is already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return
    print(f"Job Radar tracker: {url}   (Ctrl+C to stop the tracker; a run keeps going without it)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
