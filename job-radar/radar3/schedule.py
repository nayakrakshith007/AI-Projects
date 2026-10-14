"""The Windows Task Scheduler task that starts a run every morning.
It runs as you, only while you are logged in, at 08:30 by default, and 'run as soon as available' is on, so a run missed because the laptop was
off or asleep starts when it is next on. A second start while a run is going is ignored. The python.exe of this project's .venv is used."""
import subprocess
import sys

from . import config


def python_exe() -> str:
    return str(config.ROOT / ".venv" / "Scripts" / "python.exe")


def register_script(time: str = config.RUN_TIME, with_boards: bool = config.SCHEDULE_WITH_BOARDS) -> str:
    """The PowerShell that creates or replaces the task (a function so it can be tested without registering anything)."""
    py, root, name = python_exe(), str(config.ROOT), config.TASK_NAME
    return (
        f"$action = New-ScheduledTaskAction -Execute '{py}' -Argument '-m radar3 run --mode auto --started-by scheduler{"" if with_boards else " --skip-boards"}' -WorkingDirectory '{root}'\n"
        f"$trigger = New-ScheduledTaskTrigger -Daily -At '{time}'\n"
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit (New-TimeSpan -Hours 2)\n"
        "$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited\n"
        f"Register-ScheduledTask -TaskName '{name}' -Action $action -Trigger $trigger -Settings $settings -Principal $principal "
        "-Description 'Reads the AI/ML/Data job sources and rebuilds Job_Radar_V3.xlsx' -Force | Out-Null\n"
        f"Get-ScheduledTask -TaskName '{name}' | Get-ScheduledTaskInfo | Select-Object NextRunTime | Format-List\n"
    )


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)


def register(time: str = config.RUN_TIME, with_boards: bool = config.SCHEDULE_WITH_BOARDS) -> str:
    r = _ps(register_script(time, with_boards))
    return (r.stdout + r.stderr).strip()


def show() -> str:
    name = config.TASK_NAME
    r = _ps(f"$t = Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue; if ($t) {{ $i = $t | Get-ScheduledTaskInfo; "
            f"\"$($t.TaskName): state $($t.State); next run $($i.NextRunTime); last run $($i.LastRunTime); last result $($i.LastTaskResult); "
            f"start when available: $($t.Settings.StartWhenAvailable)\" }} else {{ 'not registered' }}")
    return (r.stdout + r.stderr).strip()


def remove() -> str:
    r = _ps(f"Unregister-ScheduledTask -TaskName '{config.TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue; 'removed'")
    return (r.stdout + r.stderr).strip()


if __name__ == "__main__":
    print(register(*sys.argv[1:2]))
