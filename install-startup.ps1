# Starts Mini Monitor at every logon of the current user, without a console window.
# No administrator rights needed. Usage:
#   powershell -ExecutionPolicy Bypass -File install-startup.ps1              # install and start now
#   powershell -ExecutionPolicy Bypass -File install-startup.ps1 -Uninstall   # remove
param(
    [switch]$Uninstall,
    [string]$Lang = 'fr',
    [int]$Brightness = 60
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

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "-m minimonitor --lang $Lang --brightness $Brightness" -WorkingDirectory $root
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
    -Settings $settings -Description 'Claude usage and PC dashboard on the 3.5 inch USB screen.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Installed task '$taskName' (starts at logon) and started it."
Write-Host "Log: $env:LOCALAPPDATA\MiniMonitor\minimonitor.log"
