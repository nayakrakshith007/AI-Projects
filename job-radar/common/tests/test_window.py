import json
from datetime import date, datetime

from openpyxl import Workbook

from common.window import latest_in_workbook, read_latest, record_run, resolve_hours, window_hours

NOW = datetime(2026, 10, 12, 9, 0)


def test_window_starts_at_midnight_of_the_latest_posted_date():
    assert window_hours(date(2026, 10, 11), NOW) == 33          # yesterday 00:00 to today 09:00
    assert window_hours(date(2026, 10, 9), NOW) == 81           # a missed day or two is covered
    assert window_hours(date(2026, 10, 12), NOW) == 24          # never less than 24 h
    assert window_hours(None, NOW) == 24                        # nothing known yet
    assert window_hours(date(2026, 1, 1), NOW) == 720           # capped at 30 days


def test_record_run_only_moves_forward_on_a_clean_run(tmp_path):
    state = tmp_path / "state.json"
    jobs = [{"posted_date": date(2026, 10, 10)}, {"posted_date": date(2026, 10, 11)}, {"posted_date": None}]
    assert record_run(state, jobs, error="LinkedIn rate limit", previous=None) is None
    assert not state.exists()                                    # a failed run does not move the date
    assert record_run(state, jobs, error=None) == date(2026, 10, 11)
    assert json.loads(state.read_text())["latest_posted_date"] == "2026-10-11"
    assert record_run(state, [{"posted_date": date(2026, 10, 9)}], None, previous=date(2026, 10, 11)) == date(2026, 10, 11)   # never moves back
    assert record_run(state, [], None, previous=date(2026, 10, 11)) == date(2026, 10, 11)                                       # empty run keeps it


def test_read_latest_prefers_state_then_workbook(tmp_path):
    book = tmp_path / "Site.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Site"
    ws.append(["Title", "Posted date"])
    ws.append(["a", datetime(2026, 10, 8)])
    ws.append(["b", datetime(2026, 10, 10)])
    ws.append(["c", None])
    wb.save(book)
    state = tmp_path / "state.json"
    assert latest_in_workbook(book, "Site") == date(2026, 10, 10)
    assert read_latest(state, book, "Site") == date(2026, 10, 10)        # no state yet: falls back to the workbook
    state.write_text(json.dumps({"latest_posted_date": "2026-10-11"}))
    assert read_latest(state, book, "Site") == date(2026, 10, 11)        # state wins
    assert read_latest(tmp_path / "none.json", tmp_path / "missing.xlsx", "Site") is None


def test_resolve_hours_command_line_wins(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"latest_posted_date": "2026-10-11"}))
    assert resolve_hours(48, state, tmp_path / "x.xlsx", "S", NOW)[0] == 48
    assert resolve_hours(0, state, tmp_path / "x.xlsx", "S", NOW)[0] == 0
    hours, why = resolve_hours(None, state, tmp_path / "x.xlsx", "S", NOW)
    assert hours == 33 and "2026-10-11" in why
    assert resolve_hours(None, tmp_path / "none.json", tmp_path / "x.xlsx", "S", NOW)[0] == 24


def test_resolve_hours_can_be_capped(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"latest_posted_date": "2026-09-01"}))
    hours, why = resolve_hours(None, state, tmp_path / "x.xlsx", "S", NOW, maximum=168)
    assert hours == 168 and "capped at 168 h" in why
