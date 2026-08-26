<#
Sol GONG mirror -- Windows Scheduled Task wrapper for scripts/gong_mirror.py.

WHY THIS EXISTS. docs/GONG-RELAY.md "Option D": gong2.nso.edu is unreachable
from GitHub Actions runners but answers fine from this workstation, so an
hourly local job re-publishes what it sees to the `gong-cache` branch for CI
to read over raw.githubusercontent.com. This wrapper is what Task Scheduler
actually invokes -- it exists only to (a) force unbuffered Python output
(CLAUDE.md footgun 41: without `-u`, a run killed by Task Scheduler leaves a
ZERO-BYTE log even after minutes of real work, and the only evidence left is
file mtimes in the state dir) and (b) keep a rotating log Task Scheduler's
UI does not give you on its own.

INSTALL (run once, interactively, as the account that should own the task --
this is deliberately NOT `SYSTEM`: the `gh` CLI's keyring token and the
Windows Credential Manager entry `git` uses are both per-user secrets, and
SYSTEM has no access to either). You will be prompted for your Windows
account password -- Task Scheduler stores it (encrypted, DPAPI-protected by
Windows itself) ONLY because "run whether or not the user is logged on" AND
access to those per-user secret stores both require a real logon, which is
exactly what a stored password buys and the password-less S4U logon type
does NOT (S4U cannot decrypt DPAPI-protected data, which is what the gh/git
credential stores are):

    $repoRoot = 'C:\Users\adavi\Documents\DataStories\sol'
    $action   = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repoRoot\scripts\gong-mirror-task.ps1`""
    $trigger  = New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName 'SolGongMirror' -Action $action -Trigger $trigger `
        -Settings $settings -RunLevel Limited `
        -User "$env:USERDOMAIN\$env:USERNAME" -Password '<your Windows account password>'

UNINSTALL:

    Unregister-ScheduledTask -TaskName 'SolGongMirror' -Confirm:$false

VERIFY: `Get-ScheduledTaskInfo -TaskName SolGongMirror` after the next hourly
tick -- "Last Task Result" is this script's exit code (0 = healthy mirror,
including a no-op run; 1 = failure, see scripts/gong_mirror.py's final
SUMMARY line in the log for which). Logs land in
%LOCALAPPDATA%\sol-gong-mirror\logs\.
#>

$ErrorActionPreference = 'Stop'

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $PSScriptRoot 'gong_mirror.py'

$LogDir = Join-Path $env:LOCALAPPDATA 'sol-gong-mirror\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDir "gong-mirror-$Stamp.log"

# Keep the last ~14 runs (roughly 14 hours at the intended hourly schedule --
# enough to diagnose a run of bad luck without the log directory growing
# forever). One file per run, not one ever-growing file, so a single run's
# output is trivial to grep or attach to a bug report.
$MaxLogFiles = 14
Get-ChildItem -Path $LogDir -Filter 'gong-mirror-*.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $MaxLogFiles |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Prefer the conda `sdo` interpreter (matches the rest of this pipeline's
# dev workflow) but gong_mirror.py is stdlib-only and Python-3.8-compatible
# by design specifically so the PATH fallback also works with nothing
# conda-related installed.
$CondaPython = Join-Path $env:USERPROFILE 'anaconda3\envs\sdo\python.exe'
if (Test-Path $CondaPython) {
    $PythonExe = $CondaPython
} else {
    $PythonExe = 'python'
}

# `Start-Process` with explicit -RedirectStandardOutput/-RedirectStandardError
# FILES, rather than PowerShell's `2>&1` operator, on purpose: in Windows
# PowerShell 5.1 (what Task Scheduler launches on this machine), merging a
# native process's stderr into the success stream wraps every line in a
# NativeCommandError record and sets $? to $false even when the process
# exits 0 -- indistinguishable from a real failure in a log. Start-Process's
# redirection is the plain .NET Process API and is not subject to that.
$StdOutFile = Join-Path $LogDir "gong-mirror-$Stamp.stdout.tmp"
$StdErrFile = Join-Path $LogDir "gong-mirror-$Stamp.stderr.tmp"

# -u: footgun 41. Buffered stdout means a run killed mid-flight (a missed
# wakeup, a hung request past Task Scheduler's own limits) leaves a log that
# looks like nothing happened, when in fact the state dir has partial work.
$PyArgs = @('-u', $ScriptPath) + $args

$Proc = Start-Process -FilePath $PythonExe -ArgumentList $PyArgs `
    -WorkingDirectory $RepoRoot -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $StdOutFile -RedirectStandardError $StdErrFile
$ExitCode = $Proc.ExitCode

$StdOut = if (Test-Path $StdOutFile) { Get-Content -Path $StdOutFile -Raw } else { '' }
$StdErr = if (Test-Path $StdErrFile) { Get-Content -Path $StdErrFile -Raw } else { '' }
Remove-Item -Path $StdOutFile, $StdErrFile -ErrorAction SilentlyContinue

$Header = "===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK') exit=$ExitCode ====="
$Body   = $StdOut
if ($StdErr) { $Body += "`n--- stderr ---`n$StdErr" }

# Append to the (per-run) log file AND echo to stdout, so both an operator
# watching the console (a manual test run) and Task Scheduler's log directory
# see the same thing.
Add-Content -Path $LogFile -Value $Header -Encoding utf8
Add-Content -Path $LogFile -Value $Body -Encoding utf8
Write-Output $Header
Write-Output $Body

exit $ExitCode
