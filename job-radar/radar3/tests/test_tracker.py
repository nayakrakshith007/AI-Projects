"""The progress page server: pages and data, the safety checks, and that start/stop behave (no real run is started or killed)."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from radar3 import config, tracker


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(config, "STATE_PATH", tmp_path / "run_state.json")
    monkeypatch.setattr(config, "LAST_RUN_PATH", tmp_path / "last_run.json")
    monkeypatch.setattr(config, "SOURCE_STATS_PATH", tmp_path / "stats.json")
    monkeypatch.setitem(tracker._cache, "next_run", ("Job Radar V3 Daily: state Ready; next run test", 1e18))
    srv = tracker.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def post(url, body=None, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body or {}).encode(), headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_page_and_state_and_sources(server):
    _, base = server
    code, body = get(base + "/")
    assert code == 200 and b"Job Radar V3" in body and b"/api/state" in body
    code, body = get(base + "/api/state")
    state = json.loads(body)
    assert code == 200 and state["running"] is False and state["coverage"]["working"] > 50 and "launcher_present" in state and state["port"] == config.PORT
    code, body = get(base + "/api/sources")
    rows = json.loads(body)
    from radar3.sources import load_sources
    assert len(rows) == len(load_sources()) and {r["state"] for r in rows} == {"working", "waiting", "parked", "skipped", "duplicate"}


def test_wrong_host_is_refused(server):
    _, base = server
    code, _ = get(base + "/api/state", headers={"Host": "evil.example.com"})
    assert code == 403


def test_post_needs_the_page_header_and_a_local_origin(server):
    _, base = server
    assert post(base + "/api/start", {"mode": "daily"})[0] == 403                                      # no X-Radar header
    assert post(base + "/api/start", {"mode": "daily"}, {"X-Radar": "1", "Origin": "https://evil.example.com"})[0] == 403


def test_start_is_refused_while_a_run_is_going_and_rejects_bad_modes(server, monkeypatch):
    _, base = server
    monkeypatch.setattr(tracker, "run_pid", lambda: 4242)
    code, res = post(base + "/api/start", {"mode": "daily"}, {"X-Radar": "1"})
    assert code == 200 and res == {"ok": False, "error": "a run is already going"}
    monkeypatch.setattr(tracker, "run_pid", lambda: 0)
    assert post(base + "/api/start", {"mode": "nonsense"}, {"X-Radar": "1"})[1]["ok"] is False


def test_start_launches_the_run_process_without_waiting(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    seen = {}

    class P:
        pid = 777

    def fake_popen(cmd, **kw):
        seen["cmd"] = cmd
        return P()
    monkeypatch.setattr(tracker.subprocess, "Popen", fake_popen)
    res = tracker.start_run("all")
    assert res == {"ok": True, "pid": 777, "mode": "all", "boards": True}
    assert seen["cmd"][1:6] == ["-m", "radar3", "run", "--mode", "all"] and "--no-popup" in seen["cmd"] and "progress page" in seen["cmd"]
    assert "--skip-boards" not in seen["cmd"]                                         # job boards are included by default
    tracker.start_run("daily", boards=False)
    assert "--skip-boards" in seen["cmd"]


def test_stop_ends_the_run_and_marks_the_state(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(config, "STATE_PATH", tmp_path / "run_state.json")
    monkeypatch.setattr(tracker, "run_pid", lambda: 4242)
    killed = []
    monkeypatch.setattr(tracker.subprocess, "run", lambda cmd, **kw: killed.append(cmd))
    (tmp_path / "run.lock").write_text("4242")
    (tmp_path / "run_state.json").write_text(json.dumps({"phase": "reading", "sources": {"A": {"status": "reading"}, "B": {"status": "done"}, "C": {"status": "waiting"}}}))
    assert tracker.stop_run() == {"ok": True, "stopped": 4242}
    assert killed and killed[0][:3] == ["taskkill", "/PID", "4242"] and not (tmp_path / "run.lock").exists()
    state = json.loads((tmp_path / "run_state.json").read_text())
    assert state["phase"] == "stopped" and [state["sources"][k]["status"] for k in "ABC"] == ["stopped", "done", "stopped"]


def test_a_run_that_died_shows_as_stopped_not_reading(server, tmp_path):
    _, base = server
    (tmp_path / "run_state.json").write_text(json.dumps({"phase": "reading", "sources": {}}))
    state = json.loads(get(base + "/api/state")[1])
    assert state["running"] is False and state["run"]["phase"] == "stopped"


import shutil as _shutil
import subprocess as _subprocess


@__import__("pytest").mark.skipif(_shutil.which("node") is None, reason="node not installed")
def test_the_progress_page_script_is_valid_javascript(tmp_path):
    import re
    html = (tracker.WEB_DIR / "Progress.html").read_text(encoding="utf-8")
    js = tmp_path / "page.js"
    js.write_text(re.findall(r"<script>(.*?)</script>", html, re.S)[-1], encoding="utf-8")
    r = _subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_launch_starts_server_run_and_page(monkeypatch):
    calls = []
    monkeypatch.setattr(tracker, "ensure_server", lambda port=0: calls.append("server") or True)
    monkeypatch.setattr(tracker, "start_run", lambda mode: calls.append(("run", mode)) or {"ok": True})
    monkeypatch.setattr(tracker.webbrowser, "open", lambda url: calls.append(("open", url)))
    assert tracker.launch(run=True) == 0 and calls[:2] == ["server", ("run", "all")] and calls[2][0] == "open"
    calls.clear()
    tracker.launch(run=False)
    assert ("run", "all") not in calls
