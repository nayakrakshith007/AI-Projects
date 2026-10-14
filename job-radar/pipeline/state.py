"""The live state of a run, written to pipeline/output/run_state.json while `pipeline run` works.

Whoever starts the run (the tracker button, the 09:00 task, the command line) can be watched the same way: the tracker only reads this file
and the site logs. The file is replaced atomically, so a reader never sees half of it."""
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from . import config

STATE_PATH = config.OUTPUT_DIR / "run_state.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class RunState:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or STATE_PATH
        self.lock = threading.Lock()
        self.data: dict = {}

    def _write(self) -> None:
        self.data["updated"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, self.path)

    def _event(self, text: str) -> None:
        self.data.setdefault("events", []).append({"t": _now(), "text": text})

    def begin(self, lanes: list[list[str]], scope: str, run_dir: Path, series: bool) -> None:
        with self.lock:
            sites = {}
            for i, lane in enumerate(lanes):
                for pos, name in enumerate(lane):
                    sites[name] = {"status": "waiting", "lane": i, "position": pos, "reruns": 0}
            self.data = {"pid": os.getpid(), "started": _now(), "phase": "running", "scope": scope, "series": series,
                         "run_dir": str(run_dir), "control": True, "lanes": lanes, "sites": sites, "events": [], "stats": None, "summary": None}
            self._event(f"run started: {len(sites)} sites in {len(lanes)} lane(s), scope {scope}")
            self._write()

    def site_started(self, name: str, log: Path, rerun: int) -> None:
        with self.lock:
            s = self.data["sites"].setdefault(name, {"lane": 0, "position": 0})
            s.update(status="running", started=_now(), log=str(log), reruns=rerun)
            s.pop("finished", None)
            self._event(f"{name} started" + (f" again (restart {rerun})" if rerun else ""))
            self._write()

    def site_event(self, res: dict) -> None:
        """Called for every on_done result: a finished site, or a 'stuck, starting again' notice."""
        with self.lock:
            s = self.data["sites"].setdefault(res["site"], {"lane": 0, "position": 0})
            if res["status"].startswith("stuck"):
                s["status"] = "restarting"
                self._event(f"{res['site']}: {res['status']}")
            else:
                s.update(status=res["status"], finished=_now(), minutes=res["minutes"], new=res["new"], known=res["known"],
                         total=res["total"], problems=res["problems"], exit_code=res["exit_code"], reruns=res.get("reruns", s.get("reruns", 0)))
                if res["log"]:
                    s["log"] = res["log"]
                self._event(f"{res['site']}: {res['status']} in {res['minutes']} min"
                            + (f", {res['new']} new" if res["new"] is not None else ""))
            self._write()

    def note(self, text: str) -> None:
        with self.lock:
            self._event(text)
            self._write()

    def resources(self, info: dict) -> None:
        with self.lock:
            self.data["resources"] = info
            self._write()

    def phase(self, phase: str, text: str = "") -> None:
        with self.lock:
            self.data["phase"] = phase
            if text:
                self._event(text)
            self._write()

    def finish(self, stats: dict, summary: str) -> None:
        with self.lock:
            self.data.update(phase="finished", finished=_now(), stats=stats, summary=summary)
            self._event("run finished")
            self._write()

    def fail(self, message: str) -> None:
        with self.lock:
            self.data.update(phase="failed", finished=_now(), error=message)
            self._event(f"run failed: {message}")
            self._write()


def read(path: Path | None = None) -> dict | None:
    path = path or STATE_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pid_alive(pid: int | None) -> bool:
    """True when a process with this id is still running (Windows; never signals the process)."""
    if not pid:
        return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        handle = k.OpenProcess(0x1000, False, int(pid))          # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(handle, ctypes.byref(code))
        k.CloseHandle(handle)
        return code.value == 259                                 # STILL_ACTIVE
    except Exception:
        return False


def is_running(data: dict | None) -> bool:
    """A run is going when its state file says so and its process is alive."""
    return bool(data) and data.get("phase") in ("running", "building", "stopping") and pid_alive(data.get("pid"))
