"""Why a source did not run properly, what to do, board progress from logs, reliability history, and the tracker endpoints that serve them."""
import json
import os
import threading
import urllib.request
from datetime import date

import pytest

from radar3 import config, insight, tracker

TODAY = date(2026, 10, 13)


@pytest.mark.parametrize("status,note,flag,category,severity", [
    ("needs you", "needs you; !! human check: pass it by hand", "", "Human check", "action"),
    ("failed", "HTTPError: 403 Client Error: Forbidden", "", "Blocked by the site", "info"),
    ("failed", "HTTPError: 404 Client Error: Not Found for url", "", "Address changed", "fix"),
    ("failed", "HTTPError: 429 Too Many Requests", "", "Rate limited", "retry"),
    ("failed", "stalled; no output", "", "Too slow or stalled", "retry"),
    ("failed", "ConnectionError: Max retries exceeded", "", "Site or network error", "retry"),
    ("failed", "HTTPError: 503 Server Error", "", "Site or network error", "retry"),
    ("failed", "workbook not readable: OSError", "", "File locked", "retry"),
    ("broken", "returned nothing twice in a row", "", "Broken (empty twice)", "fix"),
    ("empty", "returned nothing (watch)", "", "Returned nothing", "retry"),
    ("shrunk", "returned 5, usually about 100", "", "Far fewer jobs than usual", "retry"),
    ("degraded", "60% of the jobs have no place", "", "Layout may have changed", "fix"),
    ("", "", "never read", "Never read", "retry"),
    ("", "", "stale", "Stale data", "retry"),
    ("stopped", "", "", "Stopped by you", "retry"),
    ("failed", "something odd", "", "Failed", "retry"),
])
def test_classify(status, note, flag, category, severity):
    c = insight.classify(status, note, flag, 6)
    assert (c["category"], c["severity"]) == (category, severity) and c["suggestion"]


def test_stale_suggestion_names_the_age():
    assert "6 days" in insight.classify("", "", "stale", 6)["suggestion"]


def lines(*rows):
    return [{"date": d, "source": s, "status": st} for d, s, st in rows]


def test_fail_counts_and_current_streak():
    h = lines(("2026-10-10", "A", "done"), ("2026-10-11", "A", "failed"), ("2026-10-12", "A", "empty"), ("2026-10-13", "A", "failed"), ("2026-10-13", "B", "done"))
    fc = insight.fail_counts(h)
    assert fc["A"] == {"runs": 4, "bad": 3, "streak": 3} and fc["B"] == {"runs": 1, "bad": 0, "streak": 0}


def test_history_by_day_groups_statuses():
    h = lines(("2026-10-12", "A", "done"), ("2026-10-12", "B", "empty"), ("2026-10-12", "C", "failed"), ("2026-10-12", "D", "needs you"), ("2026-10-13", "A", "done"))
    days = insight.history_by_day(h)
    assert days[0] == {"date": "2026-10-12", "ok": 1, "warn": 1, "fail": 1, "needs": 1} and days[1]["ok"] == 1


def test_read_history_keeps_only_recent_days(tmp_path):
    p = tmp_path / "history.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines(("2026-09-01", "A", "done"), ("2026-10-12", "A", "failed"))) + "\nnot json\n")
    got = insight.read_history(p, 14, TODAY)
    assert [d["date"] for d in got] == ["2026-10-12"]


def test_problem_rows_include_run_failures_and_flags_and_sort_by_severity():
    sources = [{"id": "A", "name": "Alpha", "sheet": "remote", "reader": "r", "enabled": "yes"}, {"id": "B", "name": "Beta", "sheet": "gcc", "reader": "r", "enabled": "yes"},
               {"id": "C", "name": "Gamma", "sheet": "gcc", "reader": "r", "enabled": "yes"}, {"id": "D", "name": "Parked", "sheet": "gcc", "reader": "park", "enabled": "no"}]
    stats = {"A": {"last_ok": "2026-10-01", "counts": [5]}, "B": {"zero_runs": 1}}
    last = {"A": {"status": "failed", "note": "HTTPError: 404"}, "B": {"status": "needs you", "note": "human check"}, "C": {"status": "done", "note": ""}}
    health = [{"id": "C", "flag": "stale", "age_days": 9}]
    rows = insight.problem_rows(sources, stats, last, health, lines(("2026-10-12", "A", "failed"), ("2026-10-13", "A", "failed")), TODAY)
    assert [r["id"] for r in rows] == ["B", "A", "C"]                       # needs-you first, then fix, then retry; parked never listed
    a = next(r for r in rows if r["id"] == "A")
    assert a["category"] == "Address changed" and a["streak"] == 2 and a["bad_14d"] == 2 and a["last_ok"] == "2026-10-01"


def make_logs(tmp_path, slug, text, new=True):
    d = tmp_path / "logs" / "boards_20261013_1827"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.log").write_text(text, encoding="utf-8")
    return tmp_path / "logs"


def test_board_progress_from_the_log(tmp_path):
    root = make_logs(tmp_path, "naukri", "8 roles, 14 searches, window 24 h\n  [A] 'Data Scientist' in India, page 1: 20 new jobs\n  [B] 'Data Analyst' in India, page 1: 20 new jobs\n"
                                           "  [A] 'Data Scientist' in India, page 2: 20 new jobs\n  [C] 'ML Engineer' in India, page 1: 5 new jobs\n")
    p = insight.board_progress("naukri", root)
    assert p["planned"] == 14 and p["done"] == 3 and p["pct"] == 21 and "ML Engineer" in p["last"]


def test_board_progress_caps_at_95_and_reads_list_based_sites(tmp_path):
    root = make_logs(tmp_path, "hirist", "8 roles, 14 keywords, 22 Hirist lists (search+tag), window 24 h\n  [A] search:data-scientist page 1: 11 new jobs\n  [A] tag:data-scientist page 1: 8 new jobs\nsaving to Excel ...\n")
    p = insight.board_progress("hirist", root)
    assert p["planned"] == 22 and p["done"] == 2 and p["pct"] == 95
    root = make_logs(tmp_path, "wellfound", "8 roles, 14 keywords, 16 Wellfound page lists to read, window 24 h\n  [A] data-scientist (india) page 1: 23 new jobs\n  [A] data-scientist (remote) page 1: 24 new jobs\n")
    assert insight.board_progress("wellfound", root)["done"] == 2


def test_board_progress_none_without_a_log(tmp_path):
    assert insight.board_progress("naukri", tmp_path / "logs") is None and insight.log_tail("naukri", tmp_path / "logs") == ""


def test_log_tail_returns_the_last_lines(tmp_path):
    root = make_logs(tmp_path, "indeed", "\n".join(f"line {i}" for i in range(100)))
    assert insight.log_tail("indeed", root, 3) == "line 97\nline 98\nline 99"


# ---- endpoints
@pytest.fixture
def server(tmp_path, monkeypatch):
    for name in ("STATE_PATH", "LAST_RUN_PATH", "SOURCE_STATS_PATH", "HISTORY_PATH", "RUNS_PATH"):
        monkeypatch.setattr(config, name, tmp_path / (name.lower() + ".json"))
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setitem(tracker._cache, "next_run", ("Job Radar V3 Daily: state Ready", 1e18))
    srv = tracker.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-Radar": "1"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_info_lists_the_launcher_files_and_commands(server):
    info = get(server + "/api/info")
    names = [f["name"] for f in info["files"]]
    assert "Job Radar V3.bat" in names and "start_job_radar_v3.bat" in names and info["project"] and any("--skip-boards" in c["cmd"] for c in info["commands"]) and len(names) == 2
    assert all("what" in f and "where" in f for f in info["files"])


def test_problems_payload_shape(server, tmp_path):
    (tmp_path / "source_stats_path.json").write_text(json.dumps({"R33": {"last_status": "failed", "last_note": "HTTPError: 404", "last_ok": "2026-10-01"}}))
    p = get(server + "/api/problems")
    assert p["working"] > 50 and p["healthy"] == p["working"] - len(p["rows"])
    r = next(x for x in p["rows"] if x["id"] == "R33")
    assert r["category"] == "Address changed" and r["suggestion"] and p["categories"][0][1] >= 1


def test_state_has_free_memory_and_progress_keys(server):
    st = get(server + "/api/state")
    assert st["free_mb"] > 0 and st["progress"] == {}


def test_log_endpoint_explains_that_api_sources_have_no_log(server):
    r = get(server + "/api/log?id=R33")
    assert r["ok"] and r["text"] == "" and "API" in r["note"]
    assert get(server + "/api/log?id=NOPE")["ok"] is False


def test_open_only_allows_known_targets_and_never_runs_a_bat(server, monkeypatch):
    started = []
    monkeypatch.setattr(tracker.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    assert post(server + "/api/open", {"what": "C:/Windows/System32/cmd.exe"})["ok"] is False
    assert post(server + "/api/open", {"what": "../../etc"})["ok"] is False
    r = post(server + "/api/open", {"what": "project_run"})
    assert r["ok"] and started and started[0][:2] == ["explorer", "/select,"]               # shown in Explorer, not executed


def test_rerun_validates_ids_and_passes_only(server, monkeypatch):
    seen = {}

    class P:
        pid = 5
    monkeypatch.setattr(tracker.subprocess, "Popen", lambda cmd, **kw: seen.setdefault("cmd", cmd) and P())
    monkeypatch.setattr(tracker, "run_pid", lambda: 0)
    assert post(server + "/api/rerun", {"ids": ["NOPE"]})["ok"] is False
    assert post(server + "/api/rerun", {"ids": []})["ok"] is False
    r = post(server + "/api/rerun", {"ids": ["R33", "NOPE", "R01"]})
    assert r["ok"] and r["ids"] == ["R33", "R01"] and r["ignored"] == ["NOPE"] and r["boards"] is True
    cmd = seen["cmd"]
    assert cmd[cmd.index("--only") + 1:cmd.index("--only") + 3] == ["R33", "R01"] and "--skip-boards" not in cmd


def test_rerun_of_api_sources_only_leaves_boards_out(server, monkeypatch):
    seen = {}

    class P:
        pid = 5
    monkeypatch.setattr(tracker.subprocess, "Popen", lambda cmd, **kw: seen.setdefault("cmd", cmd) and P())
    monkeypatch.setattr(tracker, "run_pid", lambda: 0)
    r = post(server + "/api/rerun", {"ids": ["R33"]})
    assert r["ok"] and r["boards"] is False and "--skip-boards" in seen["cmd"]
