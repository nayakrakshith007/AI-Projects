"""What the progress page needs beyond the raw run state: why a source did not run properly and what to do about it, how far a job board has got,
the reliability history, and the tail of a board's log. Pure functions over the files the run already writes, so they are easy to test."""
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

from . import config

OK_STATUSES = {"done", "ok"}
WARN_STATUSES = {"empty", "shrunk", "degraded"}


def classify(status: str, note: str = "", flag: str = "", age_days: int | None = None) -> dict:
    """{'category', 'suggestion', 'severity'} for one source that did not run properly.
    severity: 'action' (needs you), 'retry' (a re-run may fix it), 'fix' (the reader or address needs work), 'info' (nothing to do)."""
    n = (note or "").lower()
    s = (status or "").lower()
    if s == "needs you" or "human check" in n:
        return {"category": "Human check", "severity": "action", "suggestion": "Open the site in Chrome, pass the check by hand, then re-run this source. The run never solves or hides a check."}
    if any(k in n for k in ("challenge", "bot protection", "captcha", "refused")) or re.search(r"\b403\b", n):
        return {"category": "Blocked by the site", "severity": "info", "suggestion": "The site refuses automated requests. It is never bypassed. Pass any check by hand, or leave it parked."}
    if re.search(r"\b(404|410)\b", n):
        return {"category": "Address changed", "severity": "fix", "suggestion": "The page or API moved. Re-read it with the browser tools (see CLAUDE.md) and fix the reader or slug in sources.csv."}
    if re.search(r"\b429\b", n) or "too many requests" in n:
        return {"category": "Rate limited", "severity": "retry", "suggestion": "The site asked us to slow down. Wait 15 minutes and re-run this source alone."}
    if s in ("stalled", "timed out") or "stalled" in n or "timed out" in n or "timeout" in n:
        return {"category": "Too slow or stalled", "severity": "retry", "suggestion": "Re-run this source alone. If it repeats, open its log to see where it stops."}
    if re.search(r"\b5\d\d\b", n) or any(k in n for k in ("connectionerror", "nameresolution", "max retries", "connection aborted", "ssl")):
        return {"category": "Site or network error", "severity": "retry", "suggestion": "Check your internet and the site, then re-run in a few minutes."}
    if "not readable" in n or "locked" in n:
        return {"category": "File locked", "severity": "retry", "suggestion": "Close the workbook in Excel (or any program using it), then re-run."}
    if s == "broken":
        return {"category": "Broken (empty twice)", "severity": "fix", "suggestion": "The page or API changed. Re-read it with the browser tools (see CLAUDE.md) and fix its reader."}
    if s == "empty" or flag == "zero runs":
        return {"category": "Returned nothing", "severity": "retry", "suggestion": "Often temporary. Re-run once; if it returns nothing again it becomes 'broken'."}
    if s == "shrunk":
        return {"category": "Far fewer jobs than usual", "severity": "retry", "suggestion": "Probably a partial read. The previous list was kept. Re-run; if it stays low the site changed."}
    if s == "degraded":
        return {"category": "Layout may have changed", "severity": "fix", "suggestion": "Most jobs have no place. Compare the reader with the live page."}
    if flag == "never read":
        return {"category": "Never read", "severity": "retry", "suggestion": "This source has not run yet. Re-run it."}
    if flag == "stale":
        return {"category": "Stale data", "severity": "retry", "suggestion": f"Last good read {age_days} days ago. Re-run; if it fails, read the reason."}
    if s == "stopped":
        return {"category": "Stopped by you", "severity": "retry", "suggestion": "The run was stopped. Re-run this source when ready."}
    return {"category": "Failed", "severity": "retry", "suggestion": "Re-run once. If it repeats, read the reason and the log."}


def read_history(path: Path | None = None, days: int = 14, today: date | None = None) -> list[dict]:
    """history.jsonl lines (one per source per run) from the last `days` days."""
    path = path or config.HISTORY_PATH
    today = today or date.today()
    cutoff = (today - timedelta(days=days)).isoformat()
    out = []
    try:
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if d.get("date", "") >= cutoff:
                out.append(d)
    except OSError:
        pass
    return out


def fail_counts(lines: list[dict]) -> dict[str, dict]:
    """Per source: runs seen, runs that were not ok, and the current streak of not-ok runs (newest last in the file)."""
    by: dict[str, list[str]] = {}
    for d in lines:
        by.setdefault(d["source"], []).append(d.get("status", ""))
    out = {}
    for sid, sts in by.items():
        streak = 0
        for st in reversed(sts):
            if st in OK_STATUSES:
                break
            streak += 1
        out[sid] = {"runs": len(sts), "bad": sum(1 for st in sts if st not in OK_STATUSES), "streak": streak}
    return out


def history_by_day(lines: list[dict]) -> list[dict]:
    """Per day: how many source reads were ok, flagged (empty, shrunk, degraded) and failed. For the reliability chart."""
    days: dict[str, dict] = {}
    for d in lines:
        row = days.setdefault(d["date"], {"date": d["date"], "ok": 0, "warn": 0, "fail": 0, "needs": 0})
        st = d.get("status", "")
        row["ok" if st in OK_STATUSES else "warn" if st in WARN_STATUSES else "needs" if st == "needs you" else "fail"] += 1
    return [days[k] for k in sorted(days)]


def problem_rows(sources: list[dict], stats: dict, run_sources: dict, health: list[dict], history: list[dict], today: date | None = None) -> list[dict]:
    """Every working source that is not healthy right now, with the category, the reason and what to do.
    run_sources: the per-source rows of the last run's state (status, note). health: health_report rows with a flag."""
    today = today or date.today()
    fails = fail_counts(history)
    flags = {h["id"]: h for h in health if h.get("flag")}
    rows = []
    for s in sources:
        if s.get("enabled") != "yes":
            continue
        sid = s["id"]
        ran = run_sources.get(sid) or {}
        status = ran.get("status", "")
        bad_run = status not in ("", "done", "ok", "waiting", "reading")
        flag = (flags.get(sid) or {}).get("flag", "")
        if not bad_run and not flag:
            continue
        st = stats.get(sid, {})
        age = (flags.get(sid) or {}).get("age_days")
        info = classify(status if bad_run else "", ran.get("note", "") if bad_run else "", flag, age)
        f = fails.get(sid, {"runs": 0, "bad": 0, "streak": 0})
        rows.append({"id": sid, "name": s["name"], "list": s["sheet"], "reader": s["reader"], "status": status if bad_run else flag, "reason": (ran.get("note") or "") if bad_run else flag,
                     **info, "last_ok": st.get("last_ok"), "age_days": age, "zero_runs": st.get("zero_runs", 0), "runs_14d": f["runs"], "bad_14d": f["bad"], "streak": f["streak"],
                     "counts": st.get("counts", [])})
    order = {"action": 0, "fix": 1, "retry": 2, "info": 3}
    rows.sort(key=lambda r: (order.get(r["severity"], 9), -r["streak"], r["name"]))
    return rows


# ---- progress of a job board, from its own log
def _header_planned(header: str) -> int | None:
    m = re.search(r"(\d+) (?:Hirist |Wellfound )?(?:page )?lists", header) or re.search(r"(\d+) (?:searches|keywords)", header)
    return int(m.group(1)) if m else None


PATTERNS = {
    "naukri": r"'([^']+)' in India, page", "linkedin": r"'([^']+)' offset", "indeed": r"'([^']+)' in India:",
    "hirist": r"\] ((?:search|tag):[\w-]+)", "wellfound": r"\] ([\w-]+ \((?:india|remote)\))",
}


def newest_board_log(slug: str, logs_root: Path | None = None) -> Path | None:
    root = logs_root or config.OUTPUT_DIR / "logs"
    best = None
    for d in sorted(root.glob("boards_*"), reverse=True)[:1]:                  # the latest boards run only
        for f in d.rglob(f"{slug}*.log"):
            if best is None or f.stat().st_mtime > best.stat().st_mtime:
                best = f
    return best


def board_progress(slug: str, logs_root: Path | None = None, now: float | None = None) -> dict | None:
    """{'pct', 'done', 'planned', 'silent_sec', 'last'} for a board that is reading, from its log: the first line says how many searches or lists are planned,
    and the later lines name the ones started. pct is capped at 95 until the site finishes."""
    f = newest_board_log(slug, logs_root)
    if not f:
        return None
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    planned = _header_planned(lines[0]) if lines else None
    done = len(set(re.findall(PATTERNS.get(slug, r"\A\Z"), text))) if slug in PATTERNS else 0
    pct = None
    if planned:
        pct = int(min(95, round(100 * done / planned))) if "saving to Excel" not in text else 95
    return {"pct": pct, "done": done, "planned": planned, "silent_sec": int((now or time.time()) - f.stat().st_mtime), "last": (lines[-1].strip()[:90] if lines else "")}


def log_tail(slug: str, logs_root: Path | None = None, lines: int = 60) -> str:
    f = newest_board_log(slug, logs_root)
    if not f:
        return ""
    try:
        return "\n".join(f.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""
