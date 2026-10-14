"""The live state of a run, written to radar3/output/run_state.json while `python -m radar3 run` works.
The progress page only reads this file, so a run started by the scheduler, the command line or the page looks the same. Replaced atomically."""
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from . import config
from .fsutil import safe_replace


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class RunState:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config.STATE_PATH
        self.lock = threading.Lock()
        self.data: dict = {}

    def _write(self) -> None:
        self.data["updated"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.data, indent=1, default=str), encoding="utf-8")
            safe_replace(tmp, self.path)
        except OSError:                                         # the live status is only for display: a locked file must never stop a run
            pass

    def _event(self, text: str) -> None:
        self.data.setdefault("events", []).append({"t": _now(), "text": text})

    def begin(self, sources: list[dict], mode: str, started_by: str = "command line") -> None:
        with self.lock:
            self.data = {"pid": os.getpid(), "started": _now(), "phase": "reading", "mode": mode, "started_by": started_by, "events": [],
                         "sources": {s["id"]: {"name": s["name"], "reader": s["reader"], "status": "waiting", "jobs": 0, "new": 0} for s in sources},
                         "summary": None}
            self._event(f"run started: {len(sources)} sources, mode {mode}")
            self._write()

    def source_started(self, sid: str) -> None:
        with self.lock:
            self.data["sources"][sid].update(status="reading", started=_now())
            self._write()

    def source_done(self, sid: str, status: str, jobs: int, seconds: float, note: str = "", new: int = 0) -> None:
        with self.lock:
            self.data["sources"][sid].update(status=status, jobs=jobs, new=new, seconds=round(seconds, 1), note=note, finished=_now())
            self._event(f"{self.data['sources'][sid]['name']}: {status}, {jobs} jobs" + (f" ({note})" if note else ""))
            self._write()

    def source_update(self, sid: str, **fields) -> None:
        """Change fields of one source's live row (status, jobs, note) without logging an event."""
        with self.lock:
            self.data["sources"].setdefault(sid, {}).update(fields)
            self._write()

    def add_event(self, text: str) -> None:
        with self.lock:
            self._event(text)
            self._write()

    def phase(self, phase: str, text: str = "") -> None:
        with self.lock:
            self.data["phase"] = phase
            if text:
                self._event(text)
            self._write()

    def finish(self, summary: dict) -> None:
        with self.lock:
            self.data.update(phase="done", summary=summary, finished=_now())
            self._event("run finished")
            self._write()
