"""The safeguards that keep a changed website from silently breaking the radar: retries, shrink and layout checks, health report, and the
contract of sources.csv (every enabled source has a reader and a well-formed slug)."""
import csv
import json
from datetime import date

import pytest

from radar3 import config, runner
from radar3.readers import READERS
from radar3.readers.common import make_job
from radar3.sources import load_sources
from radar3.state import RunState

TODAY = date(2026, 10, 13)


def jobs(n, location="Bengaluru, India"):
    s = {"id": "T", "name": "T", "cls": "A"}
    return [make_job(s, f"Data Scientist {i}", f"https://x.test/{i}", location=location, company="Acme") for i in range(n)]


# ---- judge: the health check of one read
def test_judge_normal_read():
    status, entry, note, keep = runner.judge({}, jobs(30), TODAY)
    assert (status, keep, note) == ("done", True, "") and entry["counts"] == [30] and entry["last_ok"] == "2026-10-13"


def test_judge_zero_once_then_broken():
    s1, e1, _, keep1 = runner.judge({}, [], TODAY)
    s2, e2, note2, keep2 = runner.judge(e1, [], TODAY)
    assert (s1, s2, keep1, keep2) == ("empty", "broken", False, False) and "changed" in note2


def test_judge_far_fewer_jobs_keeps_the_previous_list():
    prev = {"counts": [100, 98, 102, 101, 99], "last_count": 99}
    status, entry, note, keep = runner.judge(prev, jobs(10), TODAY)
    assert status == "shrunk" and keep is False and "kept the previous list" in note
    assert entry.get("counts") == [100, 98, 102, 101, 99]                       # the bad read does not become the new normal


def test_judge_somewhat_fewer_jobs_is_saved_but_flagged():
    prev = {"counts": [100, 100, 100], "last_count": 100}
    status, _, note, keep = runner.judge(prev, jobs(40), TODAY)
    assert status == "shrunk" and keep is True and "usually about 100" in note


def test_judge_small_sources_are_not_judged_for_shrinking():
    prev = {"counts": [8, 9, 8], "last_count": 8}
    assert runner.judge(prev, jobs(2), TODAY)[0] == "done"


def test_judge_layout_change_shows_as_missing_places():
    status, _, note, keep = runner.judge({}, jobs(20, location=""), TODAY)
    assert status == "degraded" and keep is True and "layout" in note


# ---- retries
def test_read_source_retries_a_passing_error(monkeypatch):
    calls = {"n": 0}

    def flaky(src, http):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("blip")
        return jobs(3)
    monkeypatch.setitem(READERS, "flaky", flaky)
    out, _ = runner.read_source({"reader": "flaky"}, None)
    assert len(out) == 3 and calls["n"] == 2


def test_read_source_gives_up_after_the_retries(monkeypatch):
    def down(src, http):
        raise ConnectionError("down")
    monkeypatch.setitem(READERS, "down", down)
    with pytest.raises(ConnectionError):
        runner.read_source({"reader": "down"}, None)


# ---- a shrunk read through the whole run keeps the previous jobs and the workbook
def test_run_keeps_last_good_list_when_a_source_shrinks(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SOURCE_STATS_PATH", tmp_path / "stats.json")
    monkeypatch.setattr(config, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(config, "HEALTH_PATH", tmp_path / "health.json")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    size = {"n": 60}
    monkeypatch.setitem(READERS, "sizer", lambda src, http: jobs(size["n"]))
    src = [{"id": "S1", "name": "Sizer", "company": "", "cls": "A", "reader": "sizer", "slug": "", "schedule": "daily", "enabled": "yes"}]

    def go():
        return runner.run("daily", sources=src, http=object(), today=TODAY, state=RunState(tmp_path / "state.json"), out_dir=tmp_path / "sources",
                          excel_path=tmp_path / "wb.xlsx", use_lock=False)
    go()
    size["n"] = 5
    summary = go()
    assert summary["problems"]["S1"]["status"] == "shrunk"
    assert len(runner.load_source_jobs("S1", tmp_path / "sources")) == 60
    health = json.loads((tmp_path / "health.json").read_text())
    assert health["sources"][0]["id"] == "S1" and health["sources"][0]["last_count"] == 60


def test_health_report_flags_stale_and_never_read():
    sources = [{"id": "A", "name": "A", "schedule": "daily", "enabled": "yes"}, {"id": "B", "name": "B", "schedule": "weekly", "enabled": "yes"},
               {"id": "C", "name": "C", "schedule": "daily", "enabled": "yes"}, {"id": "D", "name": "D", "schedule": "daily", "enabled": "no"}]
    stats = {"A": {"last_ok": "2026-10-08", "last_count": 5}, "B": {"last_ok": "2026-10-10", "last_count": 9}}
    rep = {r["id"]: r["flag"] for r in runner.health_report(sources, stats, TODAY)}
    assert rep == {"A": "stale", "B": "", "C": "never read"}                        # daily 5 days old; weekly 3 days old is fine; D is off


# ---- the contract of sources.csv
SLUG_SHAPE = {"workday_cxs": 3, "phenom_widget": 4, "eightfold_api": 3, "oracle_hcm": 2, "avature": 3}


def test_every_enabled_source_has_a_reader_and_a_valid_slug():
    rows = load_sources()
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert r["cls"] in "ABCDSX" and r["schedule"] in ("daily", "weekly") and r["url"].startswith("http"), r["id"]
        if r["enabled"] != "yes":
            continue
        if r["reader"] == "board_site":                      # V2's site workflows: the slug must be one of their packages
            from pipeline import config as pc
            assert r["slug"] in pc.SITE_BY_NAME, f"{r['id']} {r['name']}: unknown site workflow {r['slug']}"
            continue
        assert r["reader"] in READERS, f"{r['id']} {r['name']}: unknown reader {r['reader']}"
        parts = SLUG_SHAPE.get(r["reader"])
        if parts:
            assert len(r["slug"].split("|")) >= parts, f"{r['id']} {r['name']}: slug {r['slug']!r} needs {parts} parts"
        if r["reader"] in ("greenhouse_api", "ashby_api", "lever_api", "workable_api", "smartrecruiters", "meta_graphql"):
            assert r["slug"], f"{r['id']} {r['name']}: empty slug"


def test_every_source_row_has_exactly_one_state():
    for r in load_sources():
        state = {"X": "duplicate", "S": "skipped", "D": "parked"}.get(r["cls"]) or ("working" if r["enabled"] == "yes" else "waiting")
        assert state
        if r["cls"] in "XSD":
            assert r["enabled"] == "no", f"{r['id']} is {state} but enabled"


# ---- per-source role matches and the run log (shown on the progress page)
def test_run_writes_the_run_log_and_per_source_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SOURCE_STATS_PATH", tmp_path / "stats.json")
    monkeypatch.setattr(config, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(config, "HEALTH_PATH", tmp_path / "health.json")
    monkeypatch.setattr(config, "RUNS_PATH", tmp_path / "runs.jsonl")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setitem(READERS, "two", lambda src, http: jobs(3) + [make_job({"id": "T", "name": "T", "cls": "A"}, "Office Manager", "https://x.test/om", location="Bengaluru, India", company="Acme")])
    src = [{"id": "S1", "name": "Two", "company": "", "cls": "A", "reader": "two", "slug": "", "schedule": "daily", "enabled": "yes"}]
    monkeypatch.setattr(config, "EXCEL_PATH", tmp_path / "wb.xlsx")                      # a "real" run for this test: it logs to the (temporary) RUNS_PATH
    monkeypatch.setattr(config, "SNAPSHOT_PATH", tmp_path / "snap.json")
    monkeypatch.setattr(config, "LAST_RUN_PATH", tmp_path / "last.json")
    summary = runner.run("daily", sources=src, http=object(), today=TODAY, state=RunState(tmp_path / "state.json"), out_dir=tmp_path / "sources",
                         excel_path=tmp_path / "wb.xlsx", use_lock=False)
    assert summary["build"]["by_source"] == {"T": 3}                     # the jobs() helper tags its jobs with source id T; the unmatched title is not counted
    line = json.loads((tmp_path / "runs.jsonl").read_text().strip().splitlines()[-1])
    assert line["sources_run"] == 1 and line["ok"] == 1 and line["matched"] == 3 and line["mode"] == "daily"


def test_runs_payload_lists_newest_first(tmp_path, monkeypatch):
    from radar3 import tracker
    monkeypatch.setattr(config, "RUNS_PATH", tmp_path / "runs.jsonl")
    assert tracker.runs_payload() == []
    (tmp_path / "runs.jsonl").write_text("\n".join(json.dumps({"finished": f"2026-10-1{i}", "matched": i}) for i in range(3)) + "\n")
    assert [r["matched"] for r in tracker.runs_payload()] == [2, 1, 0]


# ---- a locked status file must never stop a run
def test_safe_replace_retries_a_locked_file(tmp_path, monkeypatch):
    from radar3 import fsutil
    calls = {"n": 0}
    real = fsutil.os.replace

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked")
        return real(a, b)
    monkeypatch.setattr(fsutil.os, "replace", flaky)
    monkeypatch.setattr(fsutil.time, "sleep", lambda s: None)
    (tmp_path / "a.tmp").write_text("x")
    fsutil.safe_replace(tmp_path / "a.tmp", tmp_path / "a.json")
    assert calls["n"] == 3 and (tmp_path / "a.json").read_text() == "x"


def test_a_locked_state_file_is_skipped_not_fatal(tmp_path, monkeypatch):
    from radar3 import state as state_mod
    monkeypatch.setattr(state_mod, "safe_replace", lambda a, b: (_ for _ in ()).throw(PermissionError("locked")))
    st = RunState(tmp_path / "state.json")
    st.begin([{"id": "S1", "name": "S", "reader": "r"}], "all")            # does not raise
    st.source_done("S1", "done", 3, 1.0)
    assert st.data["sources"]["S1"]["status"] == "done"
