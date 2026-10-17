# Single authoritative verification command for Mini Monitor.
# Usage: powershell -ExecutionPolicy Bypass -File check.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host 'FAIL: .venv missing. Create it: py -3.11 -m venv .venv ; .venv\Scripts\python -m pip install -r requirements.txt'
    exit 1
}

$failed = @()

# 1. PowerShell scripts must be pure ASCII (PowerShell 5.1 reads them as ANSI).
Get-ChildItem -Path $root -Filter *.ps1 -Recurse -File | Where-Object { $_.FullName -notlike '*\.venv\*' } | ForEach-Object {
    $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
    if ($bytes | Where-Object { $_ -gt 127 }) { $failed += "non-ASCII: $($_.Name)" }
}

# 2. Unit tests (isolated from real credentials and from the screen).
Push-Location $root
try {
    & $py -m pytest
    if ($LASTEXITCODE -ne 0) { $failed += 'pytest' }
} finally {
    Pop-Location
}

if ($failed.Count -gt 0) {
    Write-Host ('CHECK FAILED: ' + ($failed -join ', '))
    exit 1
}
Write-Host 'CHECK OK'
