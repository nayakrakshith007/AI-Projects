"""The end-of-run message box, and the Desktop launcher (a copy of the launcher on the real Desktop folder, plus a reminder while it is missing)."""
import ctypes
import subprocess
import sys
from pathlib import Path

from . import config

LAUNCHER_NAME = "Job Radar V3.bat"                         # the one file: starts the page, starts a run, opens the page
OLD_LAUNCHERS = ("Job Radar V3 Progress.bat", "Job Radar V3 Dashboard.bat")          # earlier versions had three files; they are removed
PROJECT_LAUNCHER = config.ROOT / "start_job_radar_v3.bat"


def desktop_dir() -> Path:
    """The real Desktop folder (it can be redirected to OneDrive), from Windows, not from a guess."""
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf)          # CSIDL_DESKTOP
    return Path(buf.value) if buf.value else Path.home() / "Desktop"


def launcher_text(target: Path = PROJECT_LAUNCHER) -> str:
    """A Desktop copy calls the project launcher by its full path, so it keeps working wherever it sits."""
    return f'@echo off\r\ncall "{target}"\r\n'


def launcher_present(desktop: Path | None = None) -> bool:
    path = (desktop or desktop_dir()) / LAUNCHER_NAME
    return path.exists()


def install_launcher(desktop: Path | None = None) -> Path:
    folder = desktop or desktop_dir()
    for old in OLD_LAUNCHERS:
        (folder / old).unlink(missing_ok=True)
    path = folder / LAUNCHER_NAME
    path.write_text(launcher_text(), encoding="ascii", newline="")
    return path


def message(summary: dict, desktop: Path | None = None) -> str:
    """The text of the end-of-run message: what came in, what needs attention, and the Desktop reminder while the launcher is missing."""
    b = summary["build"]
    lines = [f"{b['new_today']} new jobs today ({b['remote_open_to_india']} remote open to India, {b['bengaluru']} in Bengaluru); {b['matched']} in the workbook.",
             f"{summary['ok']} of {summary['sources_run']} sources read in {summary['seconds']:.0f} s."]
    problems = summary.get("problems") or {}
    if problems:
        lines.append(f"{len(problems)} need attention: " + ", ".join(f"{pid} ({p['status']})" for pid, p in list(problems.items())[:8]) + (" ..." if len(problems) > 8 else ""))
        lines.append("Run: python -m radar3 health   (details and what to do).")
    if not launcher_present(desktop):
        lines.append(f"Reminder: the Desktop launcher '{LAUNCHER_NAME}' is missing. Run: python -m radar3 install-launcher")
    lines.append(f"Workbook: {summary['workbook']}")
    lines.append(f"Dashboard: {config.OUTPUT_DIR / 'Dashboard.html'}")
    return "\n".join(lines)


def popup(text: str, title: str = "Job Radar V3") -> None:
    """A message box on top of other windows (MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST), shown by a separate detached process so the run
    finishes and releases its lock at once; a box nobody clicks never blocks tomorrow's run."""
    code = "import ctypes,sys; ctypes.windll.user32.MessageBoxW(None, sys.argv[1], sys.argv[2], 0x40 | 0x10000 | 0x40000)"
    exe = Path(sys.executable).with_name("pythonw.exe")
    try:
        subprocess.Popen([str(exe if exe.exists() else sys.executable), "-c", code, text, title], creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    except OSError:
        print(text)
