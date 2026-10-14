import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from pipeline import config, history, state, tracker


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "SUMMARY_PATH", tmp_path / "last_run.json")
    monkeypatch.setattr(config, "EXCEL_PATH", tmp_path / "Job_Radar.xlsx")
    monkeypatch.setattr(state, "STATE_PATH", tmp_path / "run_state.json")
    monkeypatch.setattr(history, "HISTORY_PATH", tmp_path / "history.jsonl")
    return tmp_path


def test_log_progress_counts_distinct_searches_and_reads_the_planned_total():
    text = ("15 roles, 44 searches, window 24 h\n"
            "  [Data Scientist] 'Data Scientist' in India, page 1: 20 new jobs\n"
            "  [Data Scientist] 'Data Scientist' in India, page 2: 20 new jobs\n"
            "  [Data Analyst] 'Data Analyst' in India, page 1: 20 new jobs\n")
    p = tracker.log_progress(text)
    assert (p["searches_started"], p["searches_total"]) == (2, 44) and "Data Analyst" in p["last_line"]
    hirist = "8 roles, 14 keywords, 22 Hirist lists (search+tag), window 34 h\n  [AI Engineer] search:llm page 1: 2 new jobs\n  [AI Engineer] tag:llm page 1: 1 new jobs\n"
    h = tracker.log_progress(hirist)
    assert (h["searches_started"], h["searches_total"]) == (2, 22)
    li = "15 roles, 44 searches\n  [AI Engineer] 'LLM Engineer' offset 10: 10 jobs, 10 new\n  [AI Engineer] 'LLM Engineer' offset 20: 10 jobs, 10 new\n"
    assert tracker.log_progress(li)["searches_started"] == 1


def test_run_state_file_follows_a_run(out):
    rs = state.RunState()
    log = out / "logs" / "r1" / "naukri.log"
    log.parent.mkdir(parents=True)
    log.write_text("14 searches\n  [Data Scientist] 'Data Scientist' in India, page 1: 20 new jobs\n", encoding="utf-8")
    rs.begin([["naukri"], ["hirist", "iimjobs"]], "tech", out / "logs" / "r1", False)
    d = state.read()
    assert d["phase"] == "running" and d["sites"]["hirist"]["status"] == "waiting" and d["sites"]["iimjobs"]["position"] == 1
    rs.site_started("naukri", log, 0)
    st = tracker.build_status()
    assert st["phase"] == "running" and st["run"]["sites"]["naukri"]["status"] == "running"
    assert st["run"]["sites"]["naukri"]["searches_total"] == 14 and st["run"]["sites"]["naukri"]["searches_started"] == 1
    rs.site_event({"site": "naukri", "status": "stuck, starting again (1 of 2)", "minutes": 2, "new": None, "known": None, "total": None,
                   "problems": [], "exit_code": None, "log": str(log)})
    assert state.read()["sites"]["naukri"]["status"] == "restarting"
    rs.site_event({"site": "naukri", "status": "ok", "minutes": 21.5, "new": 261, "known": 695, "total": 2330, "problems": [], "exit_code": 0, "log": str(log)})
    rs.phase("building", "building")
    rs.finish({"new_today": 12}, "done")
    done = tracker.build_status()
    assert done["phase"] == "finished" and done["run"]["sites"]["naukri"]["new"] == 261 and done["run"]["stats"]["new_today"] == 12
    assert any("starting again" in e["text"] for e in done["run"]["events"])


def test_a_run_whose_process_vanished_is_shown_as_interrupted(out):
    rs = state.RunState()
    rs.begin([["hirist"]], "tech", out / "logs" / "r2", False)
    data = state.read()
    data["pid"] = 2 ** 22 + 12345                                # no such process
    data["sites"]["hirist"]["status"] = "running"
    (out / "run_state.json").write_text(json.dumps(data), encoding="utf-8")
    st = tracker.build_status()
    assert st["phase"] == "interrupted" and st["run"]["sites"]["hirist"]["status"] == "stopped"
    assert not state.is_running(state.read())


def test_pid_alive_for_this_process_and_not_for_a_missing_one():
    assert state.pid_alive(os.getpid()) and not state.pid_alive(2 ** 22 + 99)


def test_start_is_refused_while_a_run_is_going(out, monkeypatch):
    rs = state.RunState()
    rs.begin([["hirist"]], "tech", out / "logs" / "r3", False)       # pid of this very process: alive
    code, body = tracker.start_run({"roles": "tech"})
    assert code == 409 and "already" in body["error"]


def test_start_builds_the_command_and_detaches(out, monkeypatch):
    seen = {}

    class FakeProc:
        pass

    def fake_popen(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return FakeProc()

    monkeypatch.setattr(tracker.subprocess, "Popen", fake_popen)
    code, body = tracker.start_run({"roles": "all", "series": True, "only": ["hirist", "bogus", "naukri"]})
    assert code == 200 and body["started"]
    cmd = seen["cmd"]
    assert cmd[1:5] == ["-m", "pipeline", "run", "--no-popup"] and "--series" in cmd and cmd[cmd.index("--roles") + 1] == "all"
    assert cmd[cmd.index("--only") + 1:] == ["hirist", "naukri"]
    assert seen["kw"]["creationflags"] != 0


def test_http_server_serves_page_and_status_and_guards_posts(out):
    httpd = tracker.ThreadingHTTPServer(("127.0.0.1", 0), tracker.Handler)
    port = httpd.server_port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        assert b"Job Radar V2: the daily pipeline" in urllib.request.urlopen(base + "/").read()
        assert b"Job Radar Tracker" in urllib.request.urlopen(base + "/classic").read()
        assert json.loads(urllib.request.urlopen(base + "/api/status").read())["phase"] == "idle"
        # a POST without the custom header is refused (other web pages cannot start runs)
        req = urllib.request.Request(base + "/api/start", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
        # a wrong Host header (DNS rebinding) is refused
        req = urllib.request.Request(base + "/api/status", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
        # stop with nothing running is a clean 409
        req = urllib.request.Request(base + "/api/stop", data=b"{}", method="POST", headers={"X-Tracker": "1"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 409
    finally:
        httpd.shutdown()


def test_log_view_only_reads_logs_inside_the_pipeline_logs_folder(out):
    rs = state.RunState()
    inside = out / "logs" / "r4" / "hirist.log"
    inside.parent.mkdir(parents=True)
    inside.write_text("a\nb\nc\n", encoding="utf-8")
    outside = out / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    rs.begin([["hirist", "naukri"]], "tech", out / "logs" / "r4", False)
    rs.site_started("hirist", inside, 0)
    rs.site_started("naukri", outside, 0)
    assert tracker.read_log("hirist") == "a\nb\nc"
    assert tracker.read_log("naukri") == "" and tracker.read_log("nope") == ""


def test_stop_ends_the_run_process_and_marks_the_state_stopped(out, monkeypatch):
    import subprocess
    import sys
    import time
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        rs = state.RunState()
        rs.begin([["hirist"]], "tech", out / "logs" / "r5", False)
        data = state.read()
        data["pid"] = proc.pid
        data["sites"]["hirist"]["status"] = "running"
        (out / "run_state.json").write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(tracker.runner, "stop_leftover_chromes", lambda since: 0)
        code, body = tracker.stop_run()
        assert code == 200 and body["stopped"]
        proc.wait(timeout=10)
        after = state.read()
        assert after["phase"] == "stopped" and after["sites"]["hirist"]["status"] == "stopped"
        assert tracker.build_status()["phase"] == "stopped"
        assert any("stop requested" in e["text"] for e in after["events"])
        assert not state.is_running(after)
    finally:
        proc.kill()


def test_page_hands_over_to_the_server_when_opened_as_a_file():
    for page in (tracker.HTML, tracker.CLASSIC):
        html = page.read_text(encoding="utf-8")
        assert "location.protocol === 'file:'" in html and "location.replace(home)" in html and "127.0.0.1:8770" in html
        assert "start_tracker.bat" in html                          # the message when the server is not running


def test_main_page_has_the_live_tabs_and_every_id_the_script_uses():
    import re
    html = tracker.HTML.read_text(encoding="utf-8")
    script = html[html.index("LIVE TRACKER START", html.index("<script>", html.index("</nav>"))):]
    ids = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)", script))
    missing = [i for i in ids if f'id="{i}"' not in html]
    assert not missing, missing
    assert "Live run" in html and "Performance" in html and "▶ Start workflow" in html and "n_" in html


def test_site_action_checks_the_run_and_writes_a_command_file(out, monkeypatch):
    monkeypatch.setattr(config, "CONTROL_DIR", out / "control")
    assert tracker.site_action("hirist", "stop")[0] == 409                      # no run
    rs = state.RunState()
    rs.begin([["hirist", "iimjobs"]], "tech", out / "logs" / "r6", False)       # pid of this process: alive
    assert tracker.site_action("nope", "stop")[0] == 404
    old = state.read()
    old["control"] = False
    (out / "run_state.json").write_text(json.dumps(old), encoding="utf-8")
    assert tracker.site_action("hirist", "stop")[0] == 409                      # a run from an older version cannot take commands
    old["control"] = True
    (out / "run_state.json").write_text(json.dumps(old), encoding="utf-8")
    assert tracker.site_action("hirist", "explode")[0] == 400
    code, body = tracker.site_action("hirist", "restart")
    assert code == 200 and body["queued"]
    files = list((out / "control").glob("*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text(encoding="utf-8")) == {"site": "hirist", "action": "restart"}
    rs.phase("building", "x")
    assert tracker.site_action("hirist", "stop")[0] == 409                      # too late: the workbook is being built


def test_main_page_site_cards_have_stop_and_restart_buttons():
    html = tracker.HTML.read_text(encoding="utf-8")
    assert 'data-act="restart"' in html and 'data-act="stop"' in html and "/api/site/" in html and 'id="tkToast"' in html
    assert "<button class=\"card site" not in html                   # a card is a div: buttons cannot sit inside a button
