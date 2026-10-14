"""The scheduler script, the Desktop launcher and the end-of-run message (nothing is registered or shown: all functions take paths or return text)."""
from pathlib import Path

from radar3 import config, notify, schedule

SUMMARY = {"ok": 74, "sources_run": 75, "seconds": 164.5, "workbook": r"C:\x\Job_Radar_V3.xlsx", "problems": {},
           "build": {"new_today": 12, "remote_open_to_india": 34, "bengaluru": 475, "matched": 1114}}


def test_schedule_script_has_the_morning_settings():
    s = schedule.register_script("08:30")
    assert "-Daily -At '08:30'" in s and "-StartWhenAvailable" in s and "-MultipleInstances IgnoreNew" in s
    assert "radar3 run --mode auto --started-by scheduler'" in s and "--skip-boards" not in s              # since 2026-10-14 the one daily task includes the job boards
    assert "--skip-boards" in schedule.register_script("08:30", with_boards=False) and ".venv\\Scripts\\python.exe" in s
    assert f"-TaskName '{config.TASK_NAME}'" in s and "-LogonType Interactive" in s


def test_launcher_is_written_to_the_given_desktop_and_calls_the_project_launcher(tmp_path):
    assert not notify.launcher_present(tmp_path)
    path = notify.install_launcher(tmp_path)
    assert path.name == "Job Radar V3.bat" and notify.launcher_present(tmp_path)
    assert str(notify.PROJECT_LAUNCHER) in path.read_text(encoding="ascii")
    assert Path(notify.PROJECT_LAUNCHER).exists()


def test_message_reminds_about_the_desktop_launcher_only_while_missing(tmp_path):
    assert "Reminder" in notify.message(SUMMARY, tmp_path)
    notify.install_launcher(tmp_path)
    assert "Reminder" not in notify.message(SUMMARY, tmp_path)


def test_message_lists_problem_sources(tmp_path):
    notify.install_launcher(tmp_path)
    text = notify.message({**SUMMARY, "problems": {"R42": {"status": "broken", "note": ""}, "G16": {"status": "shrunk", "note": ""}}}, tmp_path)
    assert "2 need attention" in text and "R42 (broken)" in text and "python -m radar3 health" in text


def test_only_one_desktop_file_is_written_and_old_ones_are_removed(tmp_path):
    for old in notify.OLD_LAUNCHERS:
        (tmp_path / old).write_text("x")
    notify.install_launcher(tmp_path)
    assert [f.name for f in tmp_path.iterdir()] == ["Job Radar V3.bat"]
    assert "tracker --launch" in notify.PROJECT_LAUNCHER.read_text(encoding="ascii")


def test_message_names_the_dashboard(tmp_path):
    assert "Dashboard.html" in notify.message(SUMMARY, tmp_path)


def test_a_scheduled_run_starts_the_page_server_first_and_a_manual_run_does_not(monkeypatch):
    from radar3 import __main__ as cli
    summary = {"ok": 1, "sources_run": 1, "seconds": 1, "workbook": "x", "problems": {},
               "build": {"matched": 1, "remote_open_to_india": 0, "remote_check_eligibility": 0, "bengaluru": 0, "hyderabad_chennai": 0, "rest_of_india": 0, "new_today": 0}}
    calls = []
    monkeypatch.setattr(cli, "run", lambda *a, **k: calls.append("run") or summary)
    monkeypatch.setattr(cli.tracker, "ensure_server", lambda *a, **k: calls.append("server") or True)
    assert cli.main(["run", "--started-by", "scheduler", "--no-popup"]) == 0
    assert calls == ["server", "run"]                                  # the one progress page is up before the scheduled run starts, so it shows the run
    calls.clear()
    assert cli.main(["run", "--no-popup"]) == 0
    assert calls == ["run"]
