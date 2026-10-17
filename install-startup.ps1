# Starts Mini Monitor at every logon of the current user, without a console window.
# No administrator rights needed. Usage:
#   powershell -ExecutionPolicy Bypass -File install-startup.ps1              # install and start now
#   powershell -ExecutionPolicy Bypass -File install-startup.ps1 -Uninstall   # remove
# Options: -Lang en, -Brightness 40, -Screen turing-5 (see: python -m minimonitor --help),
# -Portrait (screen standing upright), -Flip (picture upside down).
param(
    [switch]$Uninstall,
    [string]$Lang = 'fr',
    [int]$Brightness = 60,
    [string]$Screen = 'auto',
    [switch]$Portrait,
    [switch]$Flip
)
$ErrorActionPreference = 'Stop'
$taskName = 'Mini Monitor'
$root = $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($Uninstall) {
    if ($existing) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed task '$taskName'."
    } else {
        Write-Host "No task '$taskName' to remove."
    }
    exit 0
}

if (-not (Test-Path $pythonw)) {
    Write-Host 'FAIL: .venv missing. Create it first (see README).'
    exit 1
}

$arguments = "-m minimonitor --lang $Lang --brightness $Brightness --screen $Screen"
if ($Portrait) { $arguments += ' --portrait' }
if ($Flip) { $arguments += ' --flip' }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
# Runs for as long as the session lasts; restarted if it ever crashes. Priority 5 = normal:
# the default (7, below normal) starves the animation for seconds when the PC is busy.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -Priority 5

if ($existing) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal `
    -Settings $settings -Description 'Claude usage and PC dashboard on a small USB screen.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Installed task '$taskName' (starts at logon) and started it."
Write-Host "Log: $env:LOCALAPPDATA\MiniMonitor\minimonitor.log"
