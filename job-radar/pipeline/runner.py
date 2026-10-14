"""Run the site workflows in lanes (lanes side by side, the sites in a lane one after another), each site as its own process with its
own log, and report how each one ended.

A site that stops on a human check keeps what it read and shows its own pop-up; the pipeline notes it and carries on. A site that
runs past the time limit, or whose log stops changing, is stopped (its saved results stay). A site waits for free memory before it
starts, and a stalled, timed-out, failed or skipped site gets one more try, alone, at the end. Nothing here solves or hides a check."""
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config

POLL_SECONDS = 2
RETRY_STATUSES = ("failed", "stalled", "skipped")          # not "timed out": a site that ran out of time would only run out again
NEW_LINE = re.compile(r"(\d+) new, (\d+) already known\.\s+(\d+) in (\S+)")


class SiteRun:
    def __init__(self, site: config.Site, log: Path, started: float, proc: subprocess.Popen) -> None:
        self.site, self.log, self.started, self.proc = site, log, started, proc
        self.timed_out = False
        self.stalled = False
        self.stopped = False          # ended by hand from the tracker
        self.seconds = 0.0

    def result(self) -> dict:
        text = self.log.read_text(encoding="utf-8", errors="replace") if self.log.exists() else ""
        lines = text.splitlines()
        problems = [l.strip() for l in lines if l.startswith("!!")]
        m = None
        for l in reversed(lines):
            m = NEW_LINE.search(l)
            if m:
                break
        code = self.proc.returncode
        needs_you = any("human check" in p.lower() or "check_" in p.lower() for p in problems)
        if self.stopped:
            status = "stopped"
            problems = problems + ["stopped by you"]
        elif self.timed_out:
            status = "timed out"
        elif self.stalled:
            status = "stalled"
        elif code not in (0, None):
            status = "failed"
        elif needs_you:
            status = "needs you"
        elif problems:
            status = "finished with errors"
        else:
            status = "ok"
        return {"site": self.site.name, "status": status, "exit_code": code, "minutes": round(self.seconds / 60, 1),
                "new": int(m.group(1)) if m else None, "known": int(m.group(2)) if m else None, "total": int(m.group(3)) if m else None,
                "problems": problems[:3], "log": str(self.log)}


def command(site: config.Site) -> list[str]:
    extra = ["--input", str(config.ACTIVE_INPUT)] if config.ACTIVE_INPUT else []
    return [sys.executable, "-m", site.name, "search", *site.args, *extra]


def start(site: config.Site, logs_dir: Path, rerun: int = 0) -> SiteRun:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log = logs_dir / (f"{site.name}.log" if not rerun else f"{site.name}_rerun{rerun}.log")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    handle = open(log, "w", encoding="utf-8")
    proc = subprocess.Popen(command(site), cwd=config.ROOT, stdout=handle, stderr=subprocess.STDOUT, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    return SiteRun(site, log, time.time(), proc)


def kill_tree(proc: subprocess.Popen) -> None:
    """Stop a site workflow and the Chromes it started."""
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        proc.kill()


def free_mb() -> int:
    """Free physical memory in MB (a large number when it cannot be read)."""
    class _Mem(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                    ("tpage", ctypes.c_ulonglong), ("apage", ctypes.c_ulonglong), ("tvirt", ctypes.c_ulonglong), ("avirt", ctypes.c_ulonglong),
                    ("ext", ctypes.c_ulonglong)]
    try:
        m = _Mem()
        m.length = ctypes.sizeof(_Mem)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.avail / 1024 / 1024)
    except Exception:
        return 10 ** 6


def stop_leftover_chromes(since: float) -> int:
    """Stop Chromes that the workflows (Playwright) started during this run and left behind. The user's own Chrome is never touched."""
    ps = ("$t=[DateTimeOffset]::FromUnixTimeSeconds(%d).LocalDateTime; "
          "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -match 'playwright' -and $_.CreationDate -ge $t } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId } | Measure-Object | ForEach-Object Count" % int(since))
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
        return int(out or 0)
    except Exception:
        return 0


def _saving(run: SiteRun) -> bool:
    """True when the site's last log line says it is writing its Excel file (a big workbook can take minutes on a busy PC and prints nothing)."""
    try:
        with open(run.log, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 300))
            tail = f.read().decode("utf-8", errors="replace").strip().splitlines()
        return bool(tail) and "saving to Excel" in tail[-1]
    except OSError:
        return False


def _quiet_for(run: SiteRun) -> float:
    """Seconds since the site's log last changed (or since it started)."""
    try:
        return time.time() - max(run.log.stat().st_mtime, run.started)
    except OSError:
        return time.time() - run.started


def _skipped(site: config.Site, why: str) -> dict:
    return {"site": site.name, "status": "skipped", "exit_code": None, "minutes": 0.0, "new": None, "known": None, "total": None,
            "problems": [why], "log": ""}


def read_control(control_dir: Path | None = None) -> list[dict]:
    """Commands the tracker left for this run: one small JSON file per command ({"site": ..., "action": "stop" | "restart"}). Read once, then deleted."""
    control_dir = control_dir or config.CONTROL_DIR
    out = []
    for f in sorted(control_dir.glob("*.json")) if control_dir.exists() else []:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        try:
            f.unlink()
        except OSError:
            pass
    return out


def _run_lanes(lanes: list[list[config.Site]], timeout_min: float, stall_sec: float, max_reruns: int, min_free: int, memory_wait_min: float,
               logs_dir: Path, on_done, on_start=None, control=None, on_note=None) -> list[dict]:
    queues = [list(lane) for lane in lanes]
    current: list[SiteRun | None] = [None] * len(lanes)
    waiting_since: list[float | None] = [None] * len(lanes)
    results: list[dict] = []
    reruns: dict[str, int] = {}            # how many times each site was started again (names its log file)
    auto: dict[str, int] = {}              # of those, how many by the 2-minute silence rule (limited by max_reruns)
    lane_of = {s.name: i for i, lane in enumerate(lanes) for s in lane}
    by_name = {s.name: s for lane in lanes for s in lane}

    def finish(i: int, r: SiteRun) -> None:
        r.seconds = time.time() - r.started
        res = r.result()
        current[i] = None
        if r.stalled and auto.get(r.site.name, 0) < max_reruns:        # stuck: start it again straight away, in the same place in its lane
            auto[r.site.name] = auto.get(r.site.name, 0) + 1
            reruns[r.site.name] = reruns.get(r.site.name, 0) + 1
            queues[i].insert(0, r.site)
            if on_done:
                on_done(dict(res, status=f"stuck, starting again ({auto[r.site.name]} of {max_reruns})"))
            return
        res["reruns"] = reruns.get(r.site.name, 0)
        results.append(res)
        if on_done:
            on_done(res)

    def command(cmd: dict) -> None:
        name, act = cmd.get("site"), cmd.get("action")
        i = lane_of.get(name)
        if i is None or act not in ("stop", "restart"):
            return
        r = current[i] if current[i] is not None and current[i].site.name == name else None
        if r is not None:
            kill_tree(r.proc); r.proc.wait()
        queues[i] = [s for s in queues[i] if s.name != name]
        if act == "stop":
            if r is not None:
                r.stopped = True
                finish(i, r)
            else:                                                         # was waiting for its turn: skip it
                res = {"site": name, "status": "stopped", "exit_code": None, "minutes": 0.0, "new": None, "known": None, "total": None,
                       "problems": ["stopped by you before it started"], "log": ""}
                results.append(res)
                if on_done:
                    on_done(res)
            if on_note:
                on_note(f"{name}: stop requested from the tracker")
        else:                                                             # restart now, in its own lane, next in line
            if r is not None:
                current[i] = None
            reruns[name] = reruns.get(name, 0) + 1
            queues[i].insert(0, by_name[name])
            if on_note:
                on_note(f"{name}: restart requested from the tracker")

    while any(queues) or any(current):
        for cmd in (control() if control else []):
            command(cmd)
        for i in range(len(lanes)):
            r = current[i]
            if r is not None:
                if r.proc.poll() is not None:
                    finish(i, r)
                elif time.time() - r.started > config.SITE_TIMEOUTS.get(r.site.name, timeout_min) * 60:
                    r.timed_out = True
                    kill_tree(r.proc); r.proc.wait()
                    finish(i, r)
                elif _quiet_for(r) > stall_sec * (config.SAVE_STALL_FACTOR if _saving(r) else 1):
                    r.stalled = True
                    kill_tree(r.proc); r.proc.wait()
                    finish(i, r)
            if current[i] is None and queues[i]:
                site = queues[i][0]
                if free_mb() >= min_free:
                    queues[i].pop(0)
                    waiting_since[i] = None
                    current[i] = start(site, logs_dir, reruns.get(site.name, 0))
                    if on_start:
                        on_start(site.name, current[i].log, reruns.get(site.name, 0))
                else:
                    waiting_since[i] = waiting_since[i] or time.time()
                    if time.time() - waiting_since[i] > memory_wait_min * 60:
                        queues[i].pop(0)
                        waiting_since[i] = None
                        res = _skipped(site, f"not started: less than {min_free} MB of memory was free for {memory_wait_min:g} min")
                        results.append(res)
                        if on_done:
                            on_done(res)
        time.sleep(POLL_SECONDS)
    return results


def run_sites(sites: list[config.Site], timeout_min: float = config.SITE_TIMEOUT_MIN, on_done=None, lanes: list[list[config.Site]] | None = None,
              stall_sec: float = config.STALL_SEC, max_reruns: int = config.MAX_RERUNS, min_free: int = config.MIN_FREE_MB, memory_wait_min: float = config.MEMORY_WAIT_MIN,
              retry: bool = config.RETRY_FAILED, logs_dir: Path | None = None, on_start=None, control=None, on_note=None) -> list[dict]:
    """Run the sites (lanes side by side; without `lanes` every site is its own lane). Returns one result per site, in the order given."""
    lanes = lanes if lanes is not None else [[s] for s in sites]
    logs_dir = logs_dir or config.LOGS_DIR / datetime.now().strftime("%Y-%m-%d_%H%M")
    began = time.time()
    by = {r["site"]: r for r in _run_lanes(lanes, timeout_min, stall_sec, max_reruns, min_free, memory_wait_min, logs_dir, on_done, on_start, control, on_note)}
    if retry:
        for s in sites:
            if by[s.name]["status"] in RETRY_STATUSES:
                first = by[s.name]
                stop_leftover_chromes(began)
                again = _run_lanes([[s]], timeout_min, stall_sec, max_reruns, min_free, memory_wait_min, logs_dir / "retry", on_done, on_start, control, on_note)[0]
                again["retried"] = True
                again["first_status"] = first["status"]
                by[s.name] = again
    stop_leftover_chromes(began)
    return [by[s.name] for s in sites]
