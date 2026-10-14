"""Register, show or remove the daily Windows Task Scheduler task. Run as the signed-in user, so Chrome windows and pop-ups can show."""
import subprocess
import sys

from . import config


def _powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=60)


def register(time_of_day: str = config.RUN_TIME) -> tuple[bool, str]:
    """Create or replace the daily task. StartWhenAvailable runs it as soon as the PC is on if 9 AM was missed."""
    hh, mm = time_of_day.split(":")
    python = sys.executable.replace("'", "''")
    root = str(config.ROOT).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute '{python}' -Argument '-m pipeline run' -WorkingDirectory '{root}'
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours({int(hh)}).AddMinutes({int(mm)}))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName '{config.TASK_NAME}' -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description 'Job Radar V2: runs every site workflow, then builds Job_Radar.xlsx' -Force | Out-Null
'registered'
"""
    done = _powershell(script)
    return done.returncode == 0, (done.stdout + done.stderr).strip()


def show() -> str:
    script = f"""
$t = Get-ScheduledTask -TaskName '{config.TASK_NAME}' -ErrorAction SilentlyContinue
if (-not $t) {{ 'not registered'; exit }}
$i = $t | Get-ScheduledTaskInfo
"state: $($t.State); next run: $($i.NextRunTime); last run: $($i.LastRunTime); last result: $($i.LastTaskResult)"
"runs: $($t.Actions[0].Execute) $($t.Actions[0].Arguments) (in $($t.Actions[0].WorkingDirectory))"
"trigger: daily at $($t.Triggers[0].StartBoundary); start when available: $($t.Settings.StartWhenAvailable)"
"""
    done = _powershell(script)
    return (done.stdout + done.stderr).strip()


def remove() -> tuple[bool, str]:
    done = _powershell(f"Unregister-ScheduledTask -TaskName '{config.TASK_NAME}' -Confirm:$false; 'removed'")
    return done.returncode == 0, (done.stdout + done.stderr).strip()
