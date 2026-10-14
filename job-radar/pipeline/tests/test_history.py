import json
import os
from datetime import datetime, timedelta

from pipeline import config, history, state


def site(run_id, name, minutes, status="ok", new=10, scope="tech", mode="lanes", start="2026-10-12T10:00:00", reruns=0, window=24):
    return {"type": "site", "run_id": run_id, "site": name, "started": start, "finished": start, "minutes": minutes, "status": status, "new": new,
            "known": 5, "total": 100, "reruns": reruns, "problems": 0, "scope": scope, "mode": mode, "window_hours": window, "searches_total": 14,
            "source": "report", "complete": status != "stopped"}


def run(run_id, wall, scope="tech", mode="lanes", phase="finished", start="2026-10-12T10:00:00"):
    return {"type": "run", "run_id": run_id, "started": start, "finished": start, "wall_minutes": wall, "scope": scope, "mode": mode, "phase": phase,
            "sites": 2, "sites_ok": 2, "new_sum": 20, "stats": None, "resources": None}


def test_parse_header_reads_roles_window_and_total():
    h = history.parse_header("8 roles, 14 searches, window 24 h (from midnight)\n", "naukri")
    assert h == {"roles": 8, "searches_total": 14, "window_hours": 24, "scope": "tech"}
    assert history.parse_header("15 roles, 44 searches, window 34 h, 3 workers", "indeed")["scope"] == "all"
    hirist = history.parse_header("8 roles, 14 keywords, 22 Hirist lists (search+tag), window 34 h", "hirist")
    assert hirist["searches_total"] == 22 and hirist["window_hours"] == 34
    cut = history.parse_header("3 Cutshort lists, window 130 h (from midnight)", "cutshort")
    assert cut["scope"] == "tech" and cut["searches_total"] == 3 and cut["roles"] is None


def test_summary_statistics_and_filters():
    recs = []
    for i, m in enumerate([10, 12, 14, 30]):
        recs.append(site(f"r{i}", "naukri", m, new=100 + i, start=f"2026-10-1{i}T09:00:00"))
    recs += [site("r9", "naukri", 5, status="failed", new=None, start="2026-10-14T09:00:00"), site("r10", "naukri", 99, status="stopped", new=None),
             site("r11", "naukri", 50, scope="all"), site("r12", "hirist", 2), site("r13", "hirist", 3, status="finished with errors", reruns=1)]
    recs += [run("r0", 20), run("r11", 60, scope="all")]
    s = history.summary(recs, scope="tech")
    n = s["per_site"]["naukri"]
    assert n["runs"] == 5                                          # 4 ok + 1 failed; the hand-stopped run and the all-roles run are not counted
    assert n["ok"] == 4 and n["success_rate"] == 80
    assert n["median_min"] == 13.0 and n["fastest_min"] == 10 and n["slowest_min"] == 30 and n["last_status"] == "failed"
    assert n["avg_new"] == 101.5 and n["total_new"] == 406
    assert s["per_site"]["hirist"]["restarts"] == 1 and s["per_site"]["hirist"]["success_rate"] == 50
    assert s["totals"]["complete_runs"] == 1 and s["totals"]["median_wall_min"] == 20
    assert history.summary(recs, scope="all")["per_site"]["naukri"]["runs"] == 1
    assert history.summary(recs, scope="tech", mode="series")["per_site"] == {}


def test_efficiency_slowest_and_insights():
    recs = [site("a", "linkedin", 40, start="2026-10-12T09:00:00"), site("a", "hirist", 2, start="2026-10-12T09:00:00"),
            site("a", "naukri", 20, start="2026-10-12T09:00:00"), run("a", 40)]
    s = history.summary(recs)
    r = s["runs"][0]
    assert r["busy_minutes"] == 62 and r["parallel_efficiency"] == 1.55 and r["slowest_site"] == "linkedin"
    text = " ".join(s["insights"])
    assert "linkedin is the slowest site" in text and "hirist is the fastest" in text and "1.55x" in text
    assert history.summary([])["insights"] == ["Not enough history yet: complete a few runs and this fills in."]


def test_record_from_state_writes_site_and_run_lines_once(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    log = tmp_path / "logs" / "r1" / "naukri.log"
    log.parent.mkdir(parents=True)
    log.write_text("8 roles, 14 searches, window 24 h (x)\n", encoding="utf-8")
    data = {"started": "2026-10-12T13:56:00", "finished": "2026-10-12T14:20:00", "scope": "tech", "series": False, "phase": "finished",
            "run_dir": str(log.parent), "sites": {"naukri": {"status": "ok", "started": "2026-10-12T13:56:00", "finished": "2026-10-12T14:18:00",
                                                              "minutes": 22.1, "new": 261, "known": 695, "total": 2330, "problems": [], "reruns": 1, "lane": 2, "log": str(log)},
                                                  "hirist": {"status": "waiting"}},
            "events": [{"t": "2026-10-12T14:18:30", "text": "all sites done; building Job_Radar.xlsx"}],
            "stats": {"new_today": 12, "matched": 1379}, "resources": {"min_free_mb": 1200, "chrome_peak": 20, "chrome_baseline": 10}}
    assert history.record_from_state(data, path) is True
    assert history.record_from_state(data, path) is False          # the same run is never written twice
    recs = history.read_records(path)
    s = next(r for r in recs if r["type"] == "site")
    r = next(r for r in recs if r["type"] == "run")
    assert len(recs) == 2 and s["site"] == "naukri" and s["searches_total"] == 14 and s["window_hours"] == 24 and s["reruns"] == 1
    assert r["wall_minutes"] == 24.0 and r["build_seconds"] == 90 and r["sites_ok"] == 1 and r["new_sum"] == 261 and r["stats"]["new_today"] == 12
    assert r["resources"]["chrome_peak"] == 20 and r["mode"] == "lanes" and r["run_id"] == "r1"


def test_backfill_uses_reports_logs_and_marks_stopped_runs(tmp_path):
    logs = tmp_path / "logs"
    a = logs / "2026-10-12_0933"
    a.mkdir(parents=True)
    (a / "wellfound.log").write_text("8 roles, 14 keywords, 16 Wellfound page lists to read, window 34 h (x)\n", encoding="utf-8")
    (a / "wellfound_report.md").write_text("# wellfound: ok\n\n- Finished: 2026-10-12 09:52:43, took 14.6 min (last attempt)\n- Attempts: 1\n"
                                           "- Jobs: 6 new, 33 already known, 226 jobs now in the site workbook\n\n## Problems\n- none\n", encoding="utf-8")
    (a / "naukri.log").write_text("15 roles, 44 searches, window 34 h (x)\n  [Data Scientist] 'Data Scientist' in India, page 1: 20 new jobs\n", encoding="utf-8")
    (a / "linkedin.log").write_text("15 roles, 44 searches, window 35 h (x), engine jobspy\nread 3704 jobs in 114.8 min\n3184 new, 520 already known. 4280 in LinkedIn.xlsx\n", encoding="utf-8")
    path = tmp_path / "h.jsonl"
    assert history.backfill(logs, path) == 1
    assert history.backfill(logs, path) == 0                       # running it again adds nothing
    recs = {r["site"]: r for r in history.read_records(path) if r["type"] == "site"}
    assert recs["wellfound"]["status"] == "ok" and recs["wellfound"]["minutes"] == 14.6 and recs["wellfound"]["new"] == 6 and recs["wellfound"]["source"] == "report"
    assert recs["naukri"]["status"] == "stopped" and recs["naukri"]["scope"] == "all"
    assert recs["linkedin"]["minutes"] == 114.8 and recs["linkedin"]["new"] == 3184 and recs["linkedin"]["source"] == "log"
    run = next(r for r in history.read_records(path) if r["type"] == "run")
    assert run["phase"] == "stopped" and run["mode"] == "series" and run["scope"] == "all"


def test_history_api_and_experiments(tmp_path, monkeypatch):
    import threading
    import urllib.request

    from pipeline import tracker
    monkeypatch.setattr(history, "HISTORY_PATH", tmp_path / "history.jsonl")
    history._append([site("a", "hirist", 2), run("a", 2)])
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "SUMMARY_PATH", tmp_path / "last_run.json")
    monkeypatch.setattr(config, "EXCEL_PATH", tmp_path / "Job_Radar.xlsx")
    monkeypatch.setattr(state, "STATE_PATH", tmp_path / "run_state.json")
    httpd = tracker.ThreadingHTTPServer(("127.0.0.1", 0), tracker.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        body = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/history?scope=tech&mode=lanes").read())
        assert body["per_site"]["hirist"]["median_min"] == 2 and body["totals"]["runs"] == 1
        assert any(e["site"] == "naukri" and e["workers"] == 3 for e in body["experiments"])
    finally:
        httpd.shutdown()


def test_sampler_summarises_samples(monkeypatch):
    from pipeline import monitor
    monkeypatch.setattr(monitor, "chrome_count", lambda: 12)
    monkeypatch.setattr(monitor.runner, "free_mb", lambda: 2000)
    got = []
    sam = monitor.Sampler(got.append, every=0.05)
    sam._sample()
    monkeypatch.setattr(monitor.runner, "free_mb", lambda: 900)
    monkeypatch.setattr(monitor, "chrome_count", lambda: 20)
    sam._sample()
    last = got[-1]
    assert last["min_free_mb"] == 900 and last["avg_free_mb"] == 1450 and last["chrome_peak"] == 20 and last["chrome_baseline"] == 12 and last["samples"] == 2
